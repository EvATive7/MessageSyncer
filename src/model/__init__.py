import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List

import importing
import log

from .base import Adapter
from .getter_base import GetResult, Getter, GetterConfig, GetterInstanceConfig
from .pusher_base import Pusher, PusherConfig, PusherInstanceConfig
from .struct import Struct, StructElement, StructImage, StructText

adapter_classes_path = Path() / "data" / "adapter"
adapter_classes_path.mkdir(parents=True, exist_ok=True)


def _migrate():
    # TOV2
    old_paths = [Path() / "src" / "getters", Path() / "src" / "pushers"]
    logger = log.getLogger("base._migrate")

    for old_path in old_paths:
        if old_path.exists():
            log.info("Old adapters path detected")
            for item in old_path.iterdir():
                try:
                    shutil.copytree(str(item), str(adapter_classes_path / item.name))
                    log.info(f"Successfully moved {item} to new adapter_classes_path")
                except Exception as e:
                    logger.warning(
                        f"Failed to move {item} to {adapter_classes_path}: {e}"
                    )
            try:
                shutil.rmtree(str(old_path))
            except Exception as e:
                logger.warning(f"Failed to rmdir {old_path}: {e}")


_migrate()


def parse_getter(getter):
    getter = getter.split(".")
    getter.append(None)
    getter_class = getter[0]
    getter_id = getter[1]
    return getter_class, getter_id


def parse_pusher(pusher):
    _pusher = pusher.split(".", 2)
    pusher = _pusher[0]
    pusher_id = _pusher[1]
    if pusher_id == "":
        pusher_id = None
    pusher_to = _pusher[2]
    if pusher_to == "":
        pusher_to = None
    return pusher, pusher_id, pusher_to
