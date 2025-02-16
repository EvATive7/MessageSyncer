import logging
from datetime import datetime
from logging import debug, error, fatal, getLogger, info, root, warning
from pathlib import Path

import colorlog

import const

path = Path() / "data" / "log"
path.mkdir(parents=True, exist_ok=True)

log_list: list[str] = []
active_log_file: Path = None


def get_logging_handlers(log_name):
    import config

    file_level = console_level = (
        logging.DEBUG if config.main().logging.verbose else logging.INFO
    )
    log_file = path / f'{log_name}-{datetime.now().strftime("%Y-%m-%d-%H-%M-%S")}.log'
    formatstr = "%(asctime)s[%(levelname)s][%(name)s] %(message)s"

    log_file.touch(exist_ok=True)
    global active_log_file
    active_log_file = log_file

    file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
    file_handler.setLevel(file_level)
    file_handler.setFormatter(logging.Formatter(formatstr))

    console_handler = colorlog.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(
        colorlog.ColoredFormatter(
            f"%(log_color)s{formatstr}",
            log_colors={
                "DEBUG": "reset",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            },
        )
    )

    return [
        file_handler,
        console_handler,
    ]


def init():
    # [logging.getLogger(name).setLevel(logging.INFO) for name in ('peewee', 'asyncio', 'tzlocal', 'PIL.Image')]
    logging.basicConfig(level=logging.DEBUG, handlers=get_logging_handlers("root"))


init()
