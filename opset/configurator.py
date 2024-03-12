import inspect
import json
import logging
import operator
import os
import socket
import sys
import typing
import warnings
from contextlib import contextmanager
from copy import deepcopy
from functools import reduce
from typing import Any, Generic, TypeVar

import pkg_resources
import structlog
import yaml
from munch import munchify
from pydantic import BaseModel, model_validator
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from opset.gcp_secret_handler import (
    OPSET_GCP_PREFIX,
    MissingGcpSecretManagerLibrary,
    is_gcp_available,
    retrieve_gcp_secret_value,
)

OPSET_CONFIG_FILENAME = ".opset.yml"
OPSET_UNIT_TEST_FLAG = "UNIT_TEST_FLAG"
OPSET_SKIP_VALIDATION_FLAG = "OPSET_SKIP_VALIDATION"
OpsetSettingsMainModelType = TypeVar("OpsetSettingsMainModelType", bound="OpsetSettingsMainModel")

logger = logging.getLogger(__name__)

_opset_config: dict[str, Any] = {}


class OpsetSettingsBaseModel(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def parse_values(cls, values: dict[str, Any]) -> dict[str, Any]:
        unprocessed_gcp_secret_keys = []
        for k, field_info in cls.model_fields.items():
            if v := values.get(k):
                if isinstance(v, str):
                    if v.startswith(OPSET_GCP_PREFIX):
                        unprocessed_gcp_secret_keys.append(k)
                    else:
                        values[k] = cls._convert_type(v)

            else:
                field_type = typing.get_origin(field_info.annotation) or field_info.annotation
                if inspect.isclass(field_type) and issubclass(field_type, OpsetSettingsBaseModel):
                    if (default := field_info.get_default()) and default != PydanticUndefined:
                        values[k] = default
                    else:
                        values[k] = field_type()

        if not is_gcp_available() and unprocessed_gcp_secret_keys:
            raise MissingGcpSecretManagerLibrary()

        for k in unprocessed_gcp_secret_keys:
            values[k] = cls._convert_type(retrieve_gcp_secret_value(values[k], _opset_config))

        return values

    @staticmethod
    def _convert_type(value: str) -> str | bool | dict | list:
        if value.lower() in ["y", "yes", "t", "true"]:
            return True

        if value.lower() in ["n", "no", "f", "false"]:
            return False

        if isinstance(value, str) and (value.startswith("{") or value.startswith("[")):
            try:
                return typing.cast(dict | list, json.loads(value))
            except json.JSONDecodeError:
                pass

        return value


class OpsetSettingsMainModel(OpsetSettingsBaseModel):
    _opset: "Config"

    def __init__(self, _opset: "Config", **data: dict[str, Any]) -> None:
        super().__init__(**data)
        self._opset = _opset

    @property
    def opset(self) -> "Config":
        return self._opset


class OpsetLoggingConfig(OpsetSettingsBaseModel):
    date_format: str = "ISO"
    use_utc: bool = True
    min_level: str = "INFO"
    disable_processors: bool = False
    use_colors: bool = False
    json_format: bool = False
    json_event_key: str = "event"
    logger_overrides: dict[str, str] = {}


class BackwardConfig:
    def __init__(self) -> None:
        self._config: dict[str, Any] = {}

    def __getattr__(self, item: str) -> Any:
        try:
            return getattr(self._config, item)
        except AttributeError:
            raise AttributeError(f"Section [{item}] not found in the config.")

    def set_config(self, new_config: OpsetSettingsMainModelType) -> None:
        self._config = munchify(new_config.model_dump())


config = BackwardConfig()


class OpsetConfigAlreadyInitializedError(Exception):
    pass


class OpsetNotInitializedError(ValueError):
    pass


def _in_test() -> bool:
    return os.getenv(OPSET_UNIT_TEST_FLAG) is not None


class Config(Generic[OpsetSettingsMainModelType]):
    _config: OpsetSettingsMainModelType | None = None

    def __init__(
        self,
        app_name: str,
        config_model: typing.Type[OpsetSettingsMainModelType],
        config_path: str,
        setup_logging: bool = False,
        config_overrides: dict[str, Any] | None = None,
    ) -> None:
        if self._config:
            raise OpsetConfigAlreadyInitializedError("Config already initialized")

        self.app_name = app_name
        self.config_path = config_path
        self.setup_logging = setup_logging
        self.config_model = config_model

        logger.info(f"Initializing config for {self.app_name}")

        global _opset_config
        _opset_config = init_opset_config(self.config_path)

        raw_model: OpsetSettingsMainModelType = config_model.model_construct(_opset=self)

        declared_config: dict | None = None
        should_validate = False
        if not _in_test():
            local_config = self._read_yaml_config("local.yml", raise_not_found=False)
            declared_config = self._merge_configs(raw_model.model_dump(), local_config)

            self._environment_override(
                declared_config,
                raw_model.model_fields,
            )

            if config_overrides:
                declared_config = self._merge_configs(deepcopy(declared_config), config_overrides)

            should_validate = os.getenv(OPSET_SKIP_VALIDATION_FLAG) is None

        if should_validate and declared_config is not None:
            self.__set_class_config(config_model(**declared_config, _opset=self))
        else:  # pragma: no cover
            if declared_config is not None:
                raw_model = raw_model.model_copy(update=declared_config)
            self.__set_class_config(raw_model)

        self.__set_global_config()

        if self.setup_logging and hasattr(self.config, "logging"):
            if not isinstance(self.config.logging, OpsetLoggingConfig) and isinstance(self.config.logging, dict):
                self.config.logging = OpsetLoggingConfig(**self.config.logging)
            load_logging_config(self.config.logging)

    @property
    def config(self) -> OpsetSettingsMainModelType:
        if not self._config:
            raise OpsetNotInitializedError("OpsetConfig does not have an initialized config")

        return self._config

    @property
    def __formatted_name(self) -> str:
        """Convert the name of the application to be used as a prefix for fetching environment variables.

        Returns: A representation of the application name fit for fetching environment variables.
        """
        return self.app_name.upper().replace("-", "_") if self.app_name else ""

    @classmethod
    def __set_class_config(cls, internal_config: OpsetSettingsMainModelType) -> None:
        cls._config = internal_config

    def __str__(self) -> str:
        return f"Config of {self.app_name}"

    def __set_global_config(self) -> None:
        if self._config:
            global config
            config.set_config(self._config)

    @staticmethod
    def _update_pydantic_model_in_place(
        original_model: OpsetSettingsMainModelType, updated_model: OpsetSettingsMainModelType
    ) -> None:
        for f in updated_model.model_fields.keys():
            setattr(original_model, f, getattr(updated_model, f))

    @contextmanager
    def mock_config(self, config_values: dict[str, Any]) -> typing.Generator:
        old_config = deepcopy(self.config)
        declared_config = self._merge_configs(self.config.model_dump(), config_values)

        # We update the existing object to not lose any object referenced before mock_config was called
        new_config = self.config_model(**declared_config, _opset=self)
        self._update_pydantic_model_in_place(self.config, new_config)

        self.__set_global_config()
        yield
        self._update_pydantic_model_in_place(self.config, old_config)
        self.__set_global_config()

    def setup_unit_test(self, config_values: dict[str, Any]) -> None:
        declared_config = self._merge_configs(self.config.model_dump(), config_values)

        # We update the existing object to not lose any object referenced before mock_config was called
        new_config = self.config_model(**declared_config, _opset=self)
        self._update_pydantic_model_in_place(self.config, new_config)

        self.__set_global_config()

    def _get_config_file_path(self, config_name: str) -> str:
        tentative_path = pkg_resources.resource_filename(self.config_path, config_name)

        if not os.path.exists(tentative_path):
            try:
                split_path = self.config_path.rsplit(".", maxsplit=1)
                tentative_path = pkg_resources.resource_filename(split_path[0], f"{split_path[1]}/{config_name}")
            except Exception:
                pass

        return tentative_path

    def _read_yaml_config(self, config_name: str, raise_not_found: bool = True) -> dict[str, dict]:
        config_path = self._get_config_file_path(config_name)
        try:
            with open(config_path, "r") as config_file:
                return yaml.load(config_file, Loader=yaml.FullLoader) or {}
        except FileNotFoundError:
            warnings.warn(f"WARNING: Config not found at {config_path}")
            if raise_not_found:
                raise
            return {}

    def _merge_configs(self, base_config: dict, override_config: dict, current_path: list[str] | None = None) -> dict:
        """Recursively traverse two configs and apply values from the `override_config` onto the `base_config`.

        This method will also warn the user about keys present in the override dict that are
        not present in the base one, these keys will be ignored.

        Args:
            base_config: Base config, this object will be modified directly. If you wish to keep
                         your original object for later it is recommended to pass a deepcopy of it instead.
            override_config: Override config, keys matching the base config will be applied to it.
            current_path: List of keys traversed to reach the current position in the dictionaries.

        Returns:
            The resulting merged dictionary built from the other two.
        """
        if current_path is None:
            current_path = []

        for key, override_value in override_config.items():
            next_path = current_path + [key]

            if key in base_config:
                if isinstance(override_value, dict):
                    if base_config[key] is None:
                        base_config[key] = {}
                    base_config[key] = self._merge_configs(base_config[key], override_value, next_path)
                else:
                    base_config[key] = override_value
            else:
                base_config[key] = override_value
        return base_config

    @staticmethod
    def _get_dict_item_from_path(config_dict: dict, path: list[str]) -> Any:
        """Traverse a dict based on a given path.

        Args:
            config_dict: Dict to traverse
            path: List of keys representing a path in the dictionary

        Examples:
            Getting a value:
                >>> d = {"a": {"b": "1"}}
                >>> Config._get_dict_item_from_path(d, ["a", "b"])
                "1"

            Getting a sub-dictionary:
                >>> d = {"a": {"b": "1"}}
                >>> Config._get_dict_item_from_path(d, ["a"])
                {"b": "1"}

        Returns:
            The last element in the dictionary from the path provided, can be a value or a sub-dictionary
        """
        return reduce(operator.getitem, path, config_dict)

    def _get_possible_env_var_overrides(
        self,
        fields: dict[str, FieldInfo],
        *,
        prefix: str,
        current_path: list[str] | None = None,
    ) -> list[tuple[str, list[str]]]:
        """From a base config, determine the possible environment variables that can be used to override values.

        Args:
            fields: mapping of all fields and their field info from Pydantic.
            current_path: List of strings representing the path to the value in the config.
            prefix: Prefix to be applied to the environment variables.

        Returns:
            A list of tuples representing the environment variable name and path in the config
            of each possible override.
        """

        if current_path is None:
            current_path = []

        keys = []
        for key, field_info in fields.items():
            field_type = typing.get_origin(field_info.annotation) or field_info.annotation
            if inspect.isclass(field_type) and issubclass(field_type, OpsetSettingsBaseModel):
                keys.extend(
                    self._get_possible_env_var_overrides(
                        field_type.model_fields, current_path=current_path + [key], prefix=prefix
                    )
                )
            else:
                path_key = current_path + [key]
                path_key = [prefix] + path_key
                keys.append(("_".join(path_key).upper(), current_path + [key]))

        return keys

    def _environment_override(self, current_config: dict, model_fields: dict[str, FieldInfo]) -> None:
        """Override values in the config with environment variables.

        Args:
            current_config: The config that should be overridden with values from environment variables.
        """
        env_vars_overrides = self._get_possible_env_var_overrides(model_fields, prefix=self.__formatted_name)
        possible_names = []
        for env_var_name, env_var_path in env_vars_overrides:
            if env_var_name in os.environ:
                possible_names.append(env_var_name)

                if len(env_var_path) == 1:
                    current_config[env_var_path[0]] = os.environ[env_var_name]
                else:
                    cur_dict = current_config
                    for path in env_var_path[:-1]:
                        if not cur_dict.get(path):
                            cur_dict[path] = {}

                        cur_dict = cur_dict[path]

                    cur_dict[env_var_path[-1]] = os.environ[env_var_name]

        for env_key in os.environ.keys():
            if env_key.startswith(f"{self.__formatted_name}_") and env_key not in possible_names:
                warnings.warn(f"Environment variable [{env_key}] does not match any possible setting, ignoring.")


def init_opset_config(config_path: str) -> dict[str, Any]:
    """Search for opset config and load it if it exists.

    Returns:
        Opset Config or empty dict if no config found.
    """
    config_filepath = _search_for_config_file(config_path)

    if config_filepath:
        with open(config_filepath, "r") as config_file:
            return yaml.load(config_file, Loader=yaml.FullLoader) or {}

    return {}


def _search_for_config_file(dir_path: str) -> str | None:
    if os.path.exists(os.path.join(dir_path, OPSET_CONFIG_FILENAME)):
        return os.path.join(dir_path, OPSET_CONFIG_FILENAME)
    else:
        if dir_path == "/":
            return None
        parent_dir = os.path.abspath(os.path.join(dir_path, os.pardir))
        return _search_for_config_file(parent_dir)


class BaseProcessor(object):
    def __call__(self, logger: logging.Logger, name: str, event_dict: dict) -> dict:
        return event_dict


class HostNameProcessor(BaseProcessor):
    def __call__(self, logger: logging.Logger, name: str, event_dict: dict) -> dict:
        event_dict["hostname"] = socket.gethostname()
        return event_dict


def load_logging_config(
    logging_config: OpsetLoggingConfig,
    custom_processors: list[BaseProcessor] | None = None,
    custom_handlers: list[logging.Handler] | None = None,
    use_hostname_processor: bool = True,
) -> logging.Logger:
    """Load the different logging config parameters as defined in the config of the application.

    Args:
        logging_config: Opset Logging configuration object
        custom_processors: List of custom processors for log records
        custom_handlers: List of custom handlers to log records
        use_hostname_processor: Use the built-in HostNameProcessor for log records

    Returns:
        A list of handlers depending on the config if argument return_handlers has been set to True.
    """
    if logging_config.disable_processors:
        custom_processors = []
    else:
        custom_processors = custom_processors or []
        if use_hostname_processor:
            custom_processors.append(HostNameProcessor())

    pre_processors = [
        structlog.stdlib.filter_by_level,
    ]
    shared_processors: Any = [
        structlog.stdlib.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.TimeStamper(fmt=logging_config.date_format, utc=logging_config.use_utc),
        structlog.processors.UnicodeDecoder(),
        structlog.stdlib.add_logger_name,
    ] + custom_processors
    post_processors = [
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ]

    processors: Any = pre_processors + shared_processors + post_processors

    structlog.reset_defaults()
    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
        wrapper_class=structlog.stdlib.BoundLogger,
    )

    default_level_styles = structlog.dev.ConsoleRenderer.get_default_level_styles(colors=logging_config.use_colors)

    if logging_config.use_colors:
        default_level_styles["debug"] = "[34m"  # blue

    if logging_config.json_format:
        formatter = structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.processors.EventRenamer(logging_config.json_event_key),
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
            foreign_pre_chain=shared_processors,
        )
    else:
        formatter = structlog.stdlib.ProcessorFormatter(
            processor=structlog.dev.ConsoleRenderer(
                level_styles=default_level_styles, colors=logging_config.use_colors
            ),
            foreign_pre_chain=shared_processors,
        )

    stream_handler = logging.StreamHandler(stream=sys.stdout)
    stream_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = []
    root_logger.addHandler(stream_handler)
    custom_handlers = custom_handlers or []
    for handler in custom_handlers:
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    root_logger.setLevel(logging_config.min_level)

    # Add override for other loggers, usually loggers from libraries
    for logger_name, min_level in logging_config.logger_overrides.items():
        logging.getLogger(logger_name).setLevel(min_level)

    return root_logger
