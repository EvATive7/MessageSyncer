import asyncio
import concurrent
import enum
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

import aiocron
import git

import config
import const
import importing
import network
import store
import task
import util
from model import *

imported_adapter_classes: set[type] = set()
registered_getters: list[Getter] = []

# FIXME: if aiocron.crontab called in a different eventloop,
# use this to specify which eventloop the corn uses.
# If MessageSyncer run in a multi-threads mode, this will be useful.
main_event_loop = None


def _get_config():
    return config.main()


class AdapterAlreadyExist(Exception): ...


class AdapterNotFound(Exception): ...


class AdapterClassNotImported(Exception): ...


class PushTaskStatus(enum.Enum):
    PENDING = 0
    RUNNING = 1
    SUCCEED = 2
    FAILED = 3
    WAITING_RETRY = 4


class PushTask:
    logger = log.getLogger("PushTask")

    def __init__(self, article_id: str, to: str):
        self.article_id = article_id
        self.to = to
        self.id_ = f"{article_id}->{to}"

        record = store.Article.get_or_none(store.Article.id == article_id)
        if record:
            self.article = record.content
        else:
            self.article = None
        self.status = PushTaskStatus.PENDING
        self.attempt_count = 0

    async def exec(self):
        max_attempt_count = const.MAX_PUSH_ATTEMPT
        for i in range(max_attempt_count):
            attempt_flag = f"({i+1}/{max_attempt_count})"
            self.attempt_count = i + 1
            try:
                self.status = PushTaskStatus.RUNNING
                PushTask.logger.debug(f"{self.id_}: try{attempt_flag}")
                if self.article:
                    await push(self.to, self.article_id, self.article)
                PushTask.logger.debug(f"{self.id_}: finished")
                self.status = PushTaskStatus.SUCCEED
                break
            except Exception as e:
                PushTask.logger.error(
                    f"{self.id_}: failed{attempt_flag}", exc_info=True
                )
                if i + 1 >= max_attempt_count:
                    self.status = PushTaskStatus.FAILED
                    await warning(
                        Struct().text(
                            f"Failed to push to {self.to}: \n{self.article}\n: {e}"
                        )
                    )
                else:
                    self.status = PushTaskStatus.WAITING_RETRY
                    await asyncio.sleep(const.PUSH_ATTEMPT_INTERVAL)

    def __hash__(self):
        return hash(self.id_)

    def __str__(self):
        return self.id_


push_tasks: list[PushTask] = []


def _get_pusher(pusher) -> tuple[Pusher, dict]:
    pusher_class, pusher_id, pusher_to = parse_pusher(pusher)
    pusher_class = _get_or_import_class(pusher_class, adapter_classes_path)
    return pusher_class(pusher_id), {"to": pusher_to}


async def push(pusher, id_: str, content: Struct):
    pusher, detail = _get_pusher(pusher)
    preview_str = content.as_preview_str()

    logger = log.getLogger("push")
    logger.debug(f"{pusher}: {id_}: start: {preview_str}")
    await util.to_thread(pusher.push(content, **detail))
    logger.debug(f"{pusher}: {id_}: finished")


def adapter_type_is(adapter: type, type_: type):
    try:
        return type_ in adapter.__bases__
    except:
        return False


def register_getter(getter: Getter):
    update_trigger(getter)
    if _get_config().policy.refresh_when_start:
        asyncio.create_task(refresh(getter))
    registered_getters.append(getter)
    log.debug(f"Getter registered: {getter}")


def unregister_getter(getter: Getter):
    for trigger in list(getter._triggers.keys()):
        unregister_corn(getter, trigger)
    registered_getters.remove(getter)
    log.debug(f"Getter unregistered: {getter}")


def update_trigger(getter: Getter):
    triggers = getter.config.trigger
    if getter.instance_config:
        override_triggers = getter.instance_config.override_trigger
    else:
        override_triggers = None
    if override_triggers is not None:
        triggers = override_triggers

    for trigger in list(getter._triggers.keys()):
        if trigger not in triggers:
            unregister_corn(getter, trigger)

    for trigger in triggers:
        if trigger not in list(getter._triggers.keys()):
            register_corn(getter, trigger)


def register_corn(getter: Getter, trigger: str):
    cron = aiocron.crontab(
        trigger, _trigger_refresh, (getter,), start=True, loop=main_event_loop
    )
    getter._triggers[trigger] = cron
    getter.logger.debug(f"Trigger registered: {trigger}")
    return cron


def unregister_corn(getter: Getter, trigger: str):
    stop_corn(getter, trigger)
    getter._triggers.pop(trigger)
    getter.logger.debug(f"Trigger unregistered: {trigger}")


def start_corn(getter: Getter, trigger: str):
    getter._triggers[trigger].start()
    getter.logger.debug(f"Trigger started: {trigger}")


def stop_corn(getter: Getter, trigger: str):
    getter._triggers[trigger].stop()
    getter.logger.debug(f"Trigger stopped: {trigger}")


def reload_adapter_class(curclass: type):
    name = curclass.__name__
    imported_adapter_classes.remove(curclass)
    newclass = importing.from_package_import_attr(
        name, adapter_classes_path / name, name, force_reload=True
    )
    imported_adapter_classes.add(newclass)
    if adapter_type_is(newclass, Getter):
        for getter in registered_getters.copy():
            if getter.class_name == name:
                unregister_getter(getter)
        update_getters()


def install_adapter(repo_url: str):
    log.debug(f"Install adapter from {repo_url}")

    name = Path(repo_url).name.replace(".git", "")
    path = adapter_classes_path / name
    if path.exists():
        raise AdapterAlreadyExist()
    git.Repo.clone_from(repo_url, str(path.absolute()))


def uninstall_adapter(name: str):
    log.debug(f"Uninstall adapter {name}")

    path = adapter_classes_path / name
    if not path.exists():
        raise AdapterNotFound()
    path.unlink(True)


def _get_or_import_class(class_name: str, path: Path) -> type:
    if matched := [
        cls for cls in imported_adapter_classes if cls.__name__ == class_name
    ]:
        return matched[0]
    else:
        cls = importing.from_package_import_attr(
            class_name,
            path / class_name,
            class_name,
        )
        imported_adapter_classes.add(cls)
        return cls


def _parse_pairs():
    result: dict[Getter, list[str]] = {}
    for pair_str in _get_config().pair:
        try:
            getter_str, pusher_str = pair_str.split(" ", 1)
            getter_class_name, getter_id = parse_getter(getter_str)
            pusher_class_name, _, _ = parse_pusher(pusher_str)

            getter_class = _get_or_import_class(getter_class_name, adapter_classes_path)
            pusher_class = _get_or_import_class(pusher_class_name, adapter_classes_path)
        except Exception as e:
            log.warning(f"Failed to parse {pair_str}: {e}. Skipped", exc_info=True)
            continue

        if matched := [
            getter for getter in registered_getters if getter.name == getter_str
        ]:
            getter = matched[0]
        elif matched := [getter for getter in result if getter.name == getter_str]:
            getter = matched[0]
        else:
            getter = getter_class(getter_id)
            log.debug(f"{getter} initialized")

        result.setdefault(getter, []).append(pusher_str)
    return result


def update_getters():
    pairs_details = _parse_pairs()
    removed = []
    added = []
    for getter in registered_getters:
        if getter not in pairs_details:
            unregister_getter(getter)
            removed.append(getter)
    for getter in pairs_details:
        if getter not in registered_getters:
            register_getter(getter)
            added.append(getter)


async def warning(content: Struct):
    try:
        pushto = _get_config().warning.to
        for pusher in pushto:
            try:
                await push(pusher, "warning", content)
            except Exception as e:
                log.warning(f"Failed to issue alarm to {pusher}: {e}", exc_info=True)
    except Exception as e:
        log.fatal(f"Failed to issue alarm: {e}", exc_info=True)


@dataclass
class RefreshResultSingle(GetResult):
    content: list[dict]


RefreshResult = list[RefreshResultSingle]


async def _trigger_refresh(getter: Getter):
    update_trigger(getter)
    task.create_task(refresh(getter))


async def refresh(getter: Getter) -> RefreshResult:
    with network.force_proxies_patch():
        return await _refresh_worker(getter)


async def _refresh_worker(getter: Getter) -> RefreshResult:
    logger = log.getLogger("_refresh_worker")
    prefix = getter.class_name + "_"

    logger.debug(f"start")
    if not getter.available:
        logger.debug(f"unavailable. skipped")
        return []

    getter._working = True

    new_articles_during_fresh = []
    try:

        def article_already_exists(id_):
            if store.Article.get_or_none(store.Article.id == id_):
                logger.debug(f"{getter}: {id_} exists. Passed")
                return True
            logger.info(f"{getter}: got new article: {id_}")
            return False

        list_ = await util.to_thread(getter.list())
        logger.debug(f"{getter}: got latest list: {list_}")
        list_ = [
            prefix + id_ for id_ in list_ if not article_already_exists(prefix + id_)
        ]

        if list_:

            async def process_result(id_: str, result: GetResult):
                new_articles_during_fresh.append(
                    RefreshResultSingle(
                        result.user_id, result.ts, result.content.asdict()
                    )
                )
                content = result.content
                content_text = str(content)
                # logger.info(content_text)

                dopush = True
                push_passed_reason = []

                if getter._first:
                    if _get_config().policy.skip_first:
                        dopush = False
                        push_passed_reason.append("skip_first")

                for rule in _get_config().policy.block_rules:
                    if re.match(rule, content_text) or re.search(rule, content_text):
                        dopush = False
                        push_passed_reason.append(f'block_rule "{rule}"')

                if (
                    time.time() - result.ts
                ) / 3600 / 24 > _get_config().policy.article_max_ageday:
                    dopush = False
                    push_passed_reason.append("exceed article_max_ageday")

                if dopush:
                    for to in _parse_pairs()[getter]:
                        push_task = PushTask(id_, to)
                        push_tasks.append(push_task)
                        asyncio.create_task(push_task.exec())

                else:
                    logger.debug(
                        "{}: skipped to push {} because: {}".format(
                            getter, id_, ", ".join(push_passed_reason)
                        )
                    )

            async def process_fault(id_, e):
                logger.error(
                    f"{getter}: failed to get detail of {id_}: {e}", exc_info=True
                )
                await warning(
                    Struct().text(f"{getter} failed to get detail of {id_}: {e}")
                )

            def get_or_create_article(id_, detail):
                _article = store.Article.get_or_none(store.Article.id == id_)
                if not _article:
                    article = store.Article.from_getresult(id_, detail)
                    article.save(force_insert=True)

            use_merged = _get_config().policy.perf_merged_details

            if use_merged:
                try:
                    detail = await util.to_thread(
                        getter.details([id_.removeprefix(prefix) for id_ in list_])
                    )
                    detail.user_id = prefix + detail.user_id
                    [get_or_create_article(_id, detail) for _id in list_]
                    await process_result(list_, detail)
                except NotImplementedError:
                    use_merged = False
                except Exception as e:
                    await process_fault(list_, e)

            if not use_merged:
                works = []

                async def _process_signal_article(id_: str):
                    try:
                        detail = await util.to_thread(
                            getter.detail(id_.removeprefix(prefix))
                        )
                        detail.user_id = prefix + detail.user_id
                        get_or_create_article(id_, detail)
                        await process_result(id_, detail)
                    except Exception as e:
                        await process_fault(id_, e)

                for id_ in list_:
                    works.append(_process_signal_article(id_))
                await asyncio.gather(*works)

        getter._consecutive_failures_number = 0
        getter._first = False
        logger.debug(f"{getter}: finished")
    except Exception as e:
        logger.error(f"{getter}: failed: {e}", exc_info=True)

        getter._consecutive_failures_number += 1
        if (
            getter._consecutive_failures_number
            in _get_config().warning.consecutive_getter_failures_number_to_trigger_warning
        ):
            await warning(
                Struct().text(
                    f"""{getter} failed to get the latest list after {getter._consecutive_failures_number} consecutive attempts.
Latest Exception: {e}"""
                )
            )

    getter._working = False
    return new_articles_during_fresh
