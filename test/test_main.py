import asyncio
import json
import time
from datetime import datetime

import config
import core
import log
import store
from model import *

# log.init()
cur_time = time.time()
test_content_start = Struct.template1(
    content="This is the test content", ts=int(cur_time), title="Test Article"
)
test_content_end = None

last_list = [str(cur_time)]
test_config = config.MainConfig()

test_config.pair = ["CaseGetter.1 CasePusher.."]
test_config.policy.refresh_when_start = False
test_config.policy.skip_first = False


@dataclass
class CaseGetterConfig(GetterConfig):
    trigger: list[str] = field(default_factory=lambda: [])
    getter_config_key: str = "getter_config_value"


@dataclass
class CaseGetterInstanceConfig(GetterInstanceConfig):
    getter_config_instance_key: str = "getter_config_instance_value"


class CaseGetter(Getter[CaseGetterConfig, CaseGetterInstanceConfig]):
    def __init__(self, id=None) -> None:
        super().__init__(id)
        self.logger.info(f"{self.name} inited")

    async def list(self) -> list[str]:
        return last_list

    async def detail(self, id: str) -> GetResult:
        return GetResult(
            user_id="TestCase"
            + self.config.getter_config_key
            + self.instance_config.getter_config_instance_key,
            ts=int(cur_time),
            content=test_content_start,
        )


class CasePusher(Pusher):
    def __init__(self, id=None) -> None:
        super().__init__(id)

    async def push(self, content: Struct, to: str):
        global test_content_end
        test_content_end = content


async def _refresh():
    core.imported_adapter_classes.add(CaseGetter)
    core.imported_adapter_classes.add(CasePusher)

    config.main_config = test_config
    core.update_getters()

    await core.refresh(core.registered_getters[0])
    for _ in range(30):
        if all([i.status == core.PushTaskStatus.SUCCEED for i in core.push_tasks]):
            break
        await asyncio.sleep(0.1)

    assert test_content_end.asdict() == test_content_start.asdict()

    article = store.Article.get_or_none(
        store.Article.id == f"CaseGetter_{str(cur_time)}"
    )
    assert article
    assert article.content.asdict() == test_content_start.asdict()


def test_refresh():
    asyncio.run(_refresh())
