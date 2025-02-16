import asyncio
import dataclasses
import re
import shutil
import subprocess
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Type, Union

import git
import requests


def generate_function_call_str(function, *args, **kwargs):
    args_str = ", ".join(repr(arg) for arg in args)
    kwargs_str = ", ".join(f"{key}={repr(value)}" for key, value in kwargs.items())
    all_args_str = ", ".join(filter(None, [args_str, kwargs_str]))
    return f"{function}({all_args_str})"


def download(url, path: Path):
    response = requests.get(url, proxies={})
    if response.status_code == 200:
        path.write_bytes(response.content)
    else:
        raise Exception(f"Download failed: {response.status_code}")


async def download_async(url, path: Path):
    await asyncio.threads.to_thread(download, url, path)


def is_valid_url(url):
    if url is None:
        return False
    pattern = re.compile(
        r"^(https?|ftp)://"  # http, https
        r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|"  # 域名
        r"localhost|"  # local host
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|"  # IPv4 address
        r"\[?[A-F0-9]*:[A-F0-9:]+\]?)"  # IPv6 address
        r"(?::\d+)?"  # Port number (optional)
        r"(?:/?|[/?]\S+)$",
        re.IGNORECASE,
    )  # Slashes and other characters

    # Use regular expressions to match the given URL
    return re.match(pattern, url) is not None


def byte_to_MB(byte):
    return byte / (1024**2)


def get_git_version(repo_path) -> str:
    """
    Get the version of the current commit. If there's a tag exactly matching
    the current commit, return the tag name. Otherwise, return the short commit hash.

    :param repo_path: Path to the Git repository. Defaults to the current directory.
    :return: Tag name or short commit hash as the version.
    """
    try:
        # Initialize the Git repository object
        repo = git.Repo(repo_path)

        # Get the current commit
        current_commit = repo.head.commit

        # Check for exact matching tag
        tags = [tag.name for tag in repo.tags if tag.commit == current_commit]
        if tags:
            return tags[0]  # Return the first matching tag name

        # Fallback to short commit hash if no matching tag is found
        return current_commit.hexsha[:7]  # Short commit hash (first 7 characters)
    except Exception as e:
        return ""


def get_current_commit(repo_path: Path) -> str:
    """
    Gets the current commit hash value for the specified warehouse.

    :return: The hash value of the current commit
    """
    try:
        repo = git.Repo(str(repo_path))
        return repo.head.commit.hexsha
    except:
        return ""


def get_nested_value(d: dict, path):
    keys = path.split(".")
    for key in keys:
        d = d[key]
    return d


def remove_nested_key(d: dict, path):
    keys = path.split(".")
    for i, key in enumerate(keys):
        if i == len(keys) - 1:
            try:
                del d[key]
            except:
                pass
        else:
            d = d.setdefault(key, {})


def set_nested_value(d: dict, path, value):
    keys = path.split(".")
    for i, key in enumerate(keys):
        if i == len(keys) - 1:
            d[key] = value
        else:
            d = d.setdefault(key, {})


async def to_thread(coro):
    """
    Executes the coroutine in the new thread and returns the result
    :param coro: The coroutine object to be executed
    :return: Implementation results of the coroutine
    """
    future = Future()

    def thread_target():
        try:
            # Create a new event loop
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            # Execute coroutine and obtain results
            result = new_loop.run_until_complete(coro)
            future.set_result(result)
        except Exception as e:
            future.set_exception(e)
        finally:
            # Close event loop
            new_loop.close()

    # Create and start a new thread
    thread = threading.Thread(target=thread_target)
    thread.start()

    # Convert current.future to asyncio.Future and wait for the results
    return await asyncio.wrap_future(future)
