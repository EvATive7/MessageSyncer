import time
from datetime import datetime
from unittest.mock import patch

import requests

import config
import const
import log
import util


def _process_proxy(dict_: dict):
    dict_.setdefault("proxies", config.main().network.proxies)
    return dict_


original_request_method = requests.Session.request


def requests_proxy(*args, **kwargs):
    kwargs = _process_proxy(kwargs)
    logger = log.getLogger("requests_proxy")
    total_str = util.generate_function_call_str(
        "requests.Session.request", *args, **kwargs
    )
    request_str = hash(total_str)
    max_attempt_time = const.MAX_PROXY_REQUEST_ATTEMPT
    for i in range(max_attempt_time):
        logger.debug(f"{request_str}: start: {total_str}")
        attempt_flag = f"({i+1}/{max_attempt_time})"
        try:
            logger.debug(f"{request_str}: try{attempt_flag}")
            start_time = time.time()
            result = original_request_method(*args, **kwargs)
            end_time = time.time()
            logger.debug(f"{request_str}: finished after {end_time-start_time} seconds")
            return result
        except Exception as e:
            logger.warning(f"{request_str}: failed{attempt_flag}: {e}")
            if i + 1 >= max_attempt_time:
                raise e


def force_proxies_patch():
    return patch("requests.Session.request", new=requests_proxy)
