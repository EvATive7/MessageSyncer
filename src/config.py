import copy
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Lock
from types import NoneType
from typing import Generic, Type, TypeVar

import yaml

import util

path = Path() / "data" / "config"
path.mkdir(parents=True, exist_ok=True)
T = TypeVar("T")

_basic_type = [dict, int, str, list, float, set, NoneType]


def safe_asdict(content: object):
    if type(content) in _basic_type:
        return content
    else:
        return asdict(content)


class HotReloadConfigManager(Generic[T]):
    def __init__(self, config_path: Path, config_type: Type[T] = dict) -> None:
        self.type_ = config_type
        self.path = config_path
        self._rwlock = Lock()
        self._migrate_function = getattr(self.type_, "_migrate", None)

        if not self.path.exists():
            self.save(self.type_())

        if self._migrate_function:
            self.save_dict(self._migrate_function(self.dict))

    @staticmethod
    def _safe_from_dict(data_type: T, data: dict) -> T:
        """Instantiate data classes from dictionaries, including nested data classes."""

        if data_type in _basic_type:
            return data

        try:
            if data_type.__origin__ in [dict, list]:
                return data
        except AttributeError:
            pass

        fieldtypes = {
            f.name: f.type for f in data_type.__dataclass_fields__.values() if f.init
        }
        obj = data_type(
            **{
                f: (
                    HotReloadConfigManager._safe_from_dict(fieldtypes[f], data[f])
                    if isinstance(data[f], dict)
                    else data[f]
                )
                for f in data
                if f in fieldtypes
            }
        )

        return obj

    def save(self, config: T):
        self.save_dict(safe_asdict(config))

    def save_json(self, config: str):
        self.save_dict(json.loads(config))

    def save_dict(self, config: dict):
        self.save_yaml(yaml.safe_dump(config, allow_unicode=True))

    def save_yaml(self, config: str):
        with self._rwlock:
            self.path.write_text(config, "utf-8")

    @property
    def yaml(self) -> str:
        with self._rwlock:
            if self.path.exists():
                config = self.path.read_text("utf-8")
            else:
                self.path.touch()
                config = "{}"
            return config

    @property
    def dict(self) -> object:
        return yaml.safe_load(self.yaml)

    @property
    def json(self) -> str:
        return json.dumps(self.dict, ensure_ascii=False)

    @property
    def value(self) -> T:
        yaml_config = self.yaml
        dict_config = yaml.safe_load(yaml_config)
        config = HotReloadConfigManager._safe_from_dict(self.type_, dict_config)
        if yaml.safe_dump(safe_asdict(config)) != yaml_config:
            self.save(config)
        return config

    @property
    def jsonschema(self) -> T:
        return util.dataclass_to_jsonschema(self.type_)


inited_HotReloadConfigManagers: dict[str, HotReloadConfigManager] = {}


def get_config_manager(
    config_type: Type[T] = dict, name="main"
) -> HotReloadConfigManager[T]:
    if name not in inited_HotReloadConfigManagers:
        config_file = path / f"{name}.yaml"
        inited_HotReloadConfigManagers[name] = HotReloadConfigManager(
            config_type=config_type, config_path=config_file
        )

    return inited_HotReloadConfigManagers[name]


@dataclass
class MainConfig:
    @dataclass
    class LoggingConfig:
        verbose: bool = False

    @dataclass
    class APIConfig:
        token: list[str] = field(default_factory=list[str])
        port: int = 11589
        cors_allow_origins: list[str] = field(default_factory=lambda: [])

    @dataclass
    class WarningConfig:
        to: list[str] = field(default_factory=list[str])
        consecutive_getter_failures_number_to_trigger_warning: list[int] = field(
            default_factory=lambda: [2, 5, 10]
        )

    @dataclass
    class NetworkConfig:
        # This field will be passed directly to requests.request,
        # unless it is overwritten explicitly.
        proxies: dict[str, str] = field(default_factory=dict[str, str])

    @dataclass
    class PolicyConfig:
        # If refresh_when_start, a refresh will be performed when Getter is registered.
        # The results of each Getter's first refresh will not be pushed if skip_first.
        # When refresh_when_start is False and it has been a long time since the last MessageSynser refresh,
        # it is recommended to manually perform a refresh after MessageSynser is started.
        refresh_when_start: bool = True
        skip_first: bool = True
        block_rules: list[str] = field(default_factory=list[str])
        article_max_ageday: int = (
            180  # Articles exceeding the number of days corresponding to this number will not be pushed
        )

        perf_merged_details: bool = True

    pair: list[str] = field(
        default_factory=list[str]
    )  # list of pair, partially supports hotreload. Pushers take effect immediately. Getters does not support hotreload.
    warning: WarningConfig = field(default_factory=WarningConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    api: APIConfig = field(default_factory=APIConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    policy: PolicyConfig = field(default_factory=PolicyConfig)

    def _migrate(origin: dict):
        new = copy.deepcopy(origin)

        def _move_var_dict(
            old_nested_key: str, new_nested_key: str, old_dict: dict, new_dict: dict
        ):
            try:
                value = util.get_nested_value(old_dict, old_nested_key)
                util.remove_nested_key(new_dict, old_nested_key)
            except:
                return
            util.set_nested_value(new_dict, new_nested_key, value)

        # From V1 To V2
        _move_var_dict("proxies", "network.proxies", origin, new)
        _move_var_dict("refresh_when_start", "policy.refresh_when_start", origin, new)
        _move_var_dict("first_get_donot_push", "policy.skip_first", origin, new)
        _move_var_dict("block", "policy.block_rules", origin, new)
        _move_var_dict("article_max_ageday", "policy.article_max_ageday", origin, new)
        _move_var_dict("perf_merged_details", "policy.perf_merged_details", origin, new)

        return new


main_config = get_config_manager(MainConfig, "main")


def main():
    if isinstance(main_config, HotReloadConfigManager):
        return main_config.value
    else:
        return main_config
