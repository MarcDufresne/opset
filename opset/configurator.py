# configurator.py
# Alexandre Jutras, 2018-11-19
# Emilio Assuncao, 2019-01-17
# Marc-Andre Dufresne, 2020-09-10
# Copyright (c) Element AI Inc. All rights not expressly granted hereunder are reserved.

import json
import logging
import operator
import os
import socket
import sys
import warnings
from collections import defaultdict
from copy import deepcopy
from functools import reduce
from logging import Handler
from typing import Any, Dict, List, Optional, Tuple, Union, cast

import pkg_resources
import structlog
import yaml
from munch import munchify

logger = logging.getLogger(__name__)


class CriticalSettingException(Exception):
    """Thrown when a critical setting is not set.

    Happens when a critical settings was found in the default.yml config but
    had no default and was not overwritten by the local.yml config or an environment variable.
    """


class Config:
    """An object used to hold the configuration of an application.

    This object guarantees dynamic access to the config values, this ensure that the config can be imported before
    initialisation and have the values for the config receiving an update when the config is initialised.
    This class is to be initialised with the function setup_config from this module.
    """

    def __init__(self) -> None:
        self.app_name: Optional[str] = None
        self.config_path: str = ""
        self.critical_settings: bool = True
        self.setup_logging: bool = True
        self._config: Dict[str, Dict[str, Any]] = {}

    def __copy__(self) -> "Config":
        raw_config_copy: Dict[str, Any] = {}
        for section_name, section in self.items():
            raw_config_copy[section_name] = {}
            for setting, value in section.items():
                raw_config_copy[section_name][setting] = value

        config_copy = Config()
        config_copy.app_name = self.app_name
        config_copy.config_path = self.config_path
        config_copy.critical_settings = self.critical_settings
        config_copy.setup_logging = self.setup_logging
        config_copy._config = munchify(raw_config_copy)

        return config_copy

    def __getattr__(self, item: str) -> Any:
        try:
            return getattr(self._config, item)
        except AttributeError:
            raise AttributeError(f"Section [{item}] not found in the config.")

    def __str__(self) -> str:
        return f"Config of {self.app_name}"

    @property
    def __formatted_name(self) -> str:
        """Convert the name of the application to be used as a prefix for fetching environment variables.

        Returns: A representation of the application name fit for fetching environment variables.
        """
        return self.app_name.upper().replace("-", "_") if self.app_name else ""

    @staticmethod
    def _convert_type(value: str) -> Union[str, bool, int, float, Dict, List]:
        if value.lower() in ["y", "yes", "t", "true"]:
            return True

        if value.lower() in ["n", "no", "f", "false"]:
            return False

        try:
            f_value = float(value)
            if f_value % 1 == 0:
                return int(f_value)
            return f_value
        except ValueError:
            pass

        try:
            return cast(Union[str, bool, int, float, Dict, List], json.loads(value))
        except json.JSONDecodeError:
            pass

        return value

    def _get_config_file_path(self, config_name: str) -> str:
        tentative_path = pkg_resources.resource_filename(self.config_path, config_name)

        if not os.path.exists(tentative_path):
            try:
                split_path = self.config_path.rsplit(".", maxsplit=1)
                tentative_path = pkg_resources.resource_filename(split_path[0], f"{split_path[1]}/{config_name}")
            except Exception:
                pass

        return tentative_path

    def _read_yaml_config(self, config_name: str, raise_not_found: bool = True) -> Dict[str, Dict]:
        config_path = self._get_config_file_path(config_name)
        try:
            with open(config_path, "r") as config_file:
                if hasattr(yaml, "FullLoader"):
                    # pyyaml 5.1+
                    return yaml.load(config_file, Loader=yaml.FullLoader) or {}
                # pyyaml 3.13
                return yaml.load(config_file) or {}
        except FileNotFoundError:
            warnings.warn(f"WARNING: Config not found at {config_path}")
            if raise_not_found:
                raise
            return {}

    def _build_critical_setting_exception(self, missing_settings: List[List[str]]) -> CriticalSettingException:
        message = "\n"
        for missing in missing_settings:
            message += f"- Missing setting [{'.'.join(missing)}].\n"
        message += (
            f"\nPlease define missing values in "
            f"[{self._get_config_file_path('local.yml')}] or as environment values as "
            f"'{self.__formatted_name}_<SECTION>_<SETTING>'."
        )
        return CriticalSettingException(message)

    def _merge_configs(
        self, base_config: Dict, override_config: Dict, current_path: Optional[List[str]] = None
    ) -> Dict:
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
            elif len(current_path) > 1:
                # Only allow overriding keys in a section, not at the top level to keep behaviour from 1.x
                base_config[key] = override_value
            else:
                warnings.warn(f"Override [{'.'.join(next_path)}] not found in base config, ignoring.")
        return base_config

    def _get_possible_env_var_overrides(
        self, current_config: Dict, current_path: Optional[List[str]] = None, prefix: str = ""
    ) -> List[Tuple[str, List[str]]]:
        """From a base config, determine the possible environment variables that can be used to override values.

        Args:
            current_config: The base config to be used for determining the possible names.
            current_path: List of strings representing the path to the value in the config.
            prefix: Prefix to be applied to the environment variables.

        Returns:
            A list of tuples representing the environment variable name and path in the config
            of each possible override.
        """
        if current_path is None:
            current_path = []

        keys = []
        for key, value in current_config.items():
            if isinstance(value, dict) and len(value):
                keys.extend(
                    self._get_possible_env_var_overrides(
                        current_config[key], current_path=current_path + [key], prefix=prefix
                    )
                )
            else:
                path_key = current_path + [key]
                if prefix:
                    path_key = [prefix] + path_key
                keys.append(("_".join(path_key).upper(), current_path + [key]))

        return keys

    def _environment_override(
        self, current_config: Dict, default_config: Dict, critical_settings: bool = False
    ) -> None:
        """Override values in the config with environment variables.

        Args:
            current_config: The config that should be overridden with values from environment variables.
            default_config: The base config used to generate possible environment variable names
            critical_settings: If True, after overriding values, raise a
                               `CriticalSettingException` for any missing value.

        Raises:
            CriticalSettingException: If any value is missing in the config after overriding them,
                                      but only if `critical_settings` is `True`
        """
        env_vars_overrides = self._get_possible_env_var_overrides(default_config, prefix=self.__formatted_name)
        possible_names = []
        for env_var_name, env_var_path in env_vars_overrides:
            if env_var_name in os.environ:
                possible_names.append(env_var_name)
                # traverse the config dict based on the path and set the value
                self._get_dict_item_from_path(current_config, env_var_path[:-1])[env_var_path[-1]] = self._convert_type(
                    os.environ[env_var_name]
                )

        # handling of critical setting flag
        if critical_settings:
            missing_settings_paths = []
            for _, env_var_path in env_vars_overrides:
                if self._get_dict_item_from_path(current_config, env_var_path) is None:
                    missing_settings_paths.append(env_var_path)
            if missing_settings_paths:
                raise self._build_critical_setting_exception(missing_settings_paths)

        for env_key in os.environ.keys():
            if env_key.startswith(f"{self.__formatted_name}_") and env_key not in possible_names:
                warnings.warn(f"Environment variable [{env_key}] does not match any possible setting, ignoring.")

    @staticmethod
    def _get_dict_item_from_path(config_dict: Dict, path: List[str]) -> Any:
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

    def setup_config(
        self,
        app_name: str,
        config_path: str,
        critical_settings: bool = True,
        setup_logging: bool = False,
        reload_config: bool = False,
    ) -> None:
        """Read the config file and load them in the config object.

        Order of overwrites:
            default.yml -> local.yml -> environment variables

        Args:
            app_name: The name of the application, usually the name of the repo. Ex: my-super-app. This will be
                used for finding the prefix to the environment variables. The name of the app will be uppercased and
                dashes be replaced by underscores.
            config_path: A python path to where the configuration files are. Using python notation for the path and
                starting from the root of the application.
                Ex: tasks.config would mean that the config files are situated in the package config of the package
                tasks from the root of the repo my_task_app.
            critical_settings: A boolean that specifies if the settings declared in the default.yml config
                should be interpreted as critical or not. If set to True, this function will throw an exception if a
                setting declared in default.yml has no default and it is not overwritten by a setting in
                the local.yml config or an environment variable.
            setup_logging: Whether the logging config should be loaded immediately after the config has been
                loaded. Default to True.
            reload_config: Whether to force reload the config or not, by default if the config has already been
                loaded once it will skip reloading, by setting reload_config to True you ensure that the config will
                be reloaded.

        Raises:
            CriticalSettingException when a critical settings is not defined in local.yml and as env variable.
        """
        # Skip if the config has already been initialised
        if self._config and not reload_config:
            return

        self.app_name = app_name
        self.config_path = config_path
        self.critical_settings = critical_settings
        self.setup_logging = setup_logging
        self._config = defaultdict(dict)

        logger.info(f"Initializing config for {self.app_name}")

        default_config = self._read_yaml_config("default.yml", raise_not_found=True)
        local_config = self._read_yaml_config("local.yml", raise_not_found=False)

        declared_settings = self._merge_configs(deepcopy(default_config), local_config)

        self._environment_override(declared_settings, default_config, critical_settings=critical_settings)

        # Cast config to munch so it behaves like an object instead of a dict
        self._config = munchify(declared_settings)

        if self.setup_logging:
            load_logging_config()

    def setup_unit_test_config(
        self, app_name: str, config_path: str, config_values: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> None:
        """Prepare the config object specifically to be used for unit tests.

        Load default.yml and either apply the content of unit_test.yaml if it is available and then the
        environment variables. The content of the param config_values will be used as a final overwrite.

        Order of overwrites with unit_test.yml:

            default.yml -> unit_test.yml -> environment variables -> config_values

        Order of overwrites without unit_test.yml:

            default.yml -> environment variables -> config_values

        Args:
            app_name: The name of the application, usually the name of the repo. Ex: my-super-app. This will be
                used for finding the prefix to the environment variables. The name of the app will be uppercased and
                dashes be replaced by underscores.
            config_path: A python path to where the configuration files are. Using python notation for the path and
                starting from the root of the application.
                Ex: tasks.config would mean that the config files are situated in the package config of the package
                tasks from the root of the repo my_task_app.
            config_values: A dictionary mimicking the structure of the config files, to be applied as an overwrite on
                top of default + unit_test config (if available) and env variables.
        """
        self.app_name = app_name
        self.config_path = config_path
        self._config = defaultdict(dict)

        config_values = config_values or {}

        logger.info("Initializing config for unit tests")

        default_config = self._read_yaml_config("default.yml", raise_not_found=True)
        test_config = self._read_yaml_config("unit_test.yml", raise_not_found=False)

        if test_config:  # Test config available, assuming local dev. default -> unit_test -> env vars -> config_values
            declared_settings = self._merge_configs(deepcopy(default_config), test_config)
        else:  # Test config available, assuming local dev. default -> env vars -> config_values
            declared_settings = default_config

        # env var overrides
        self._environment_override(declared_settings, default_config, critical_settings=False)

        # override with config values
        declared_settings = self._merge_configs(deepcopy(declared_settings), config_values)

        # Cast config to munch so it behaves like an object instead of a dict
        self._config = munchify(declared_settings)

    def overwrite_from_dict(
        self, config_overwrite: Dict[str, Dict[str, Any]], base_config: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> None:
        """Apply a dictionary structure mimicking the config files to the config, overwriting matching settings.

        Args:
            config_overwrite: A dictionary structure mimicking the config files.
            base_config: The config being overwritten, default to the main config object of Config.
        """
        base_config = base_config or self._config
        self._merge_configs(base_config, config_overwrite)


config = Config()


def setup_config(
    app_name: str,
    config_path: str,
    critical_settings: bool = True,
    setup_logging: bool = False,
    reload_config: bool = False,
) -> None:
    """Initialize the config and wraps the setup functionality of the singleton object.

    Args:
        app_name: The name of the application, usually the name of the repo. Ex: my-super-app. This will be used
            for finding the prefix to the environment variables. The name of the app will be uppercased and dashes
            be replaced by underscores.
        config_path: A python path to where the configuration files are. Using python notation for the path and
                starting from the root of the application.
                Ex: tasks.config would mean that the config files are situated in the package config of the package
                tasks from the root of the repo my_task_app.
        critical_settings: A boolean that specifies if the settings declared in the default.yml config
                should be interpreted as critical or not. If set to True, this function will throw an exception if a
                setting declared in default.yml has no default and it is not overwritten by a setting in
                the local.yml config or an environment variable.
        setup_logging: Whether the logging config should be loaded immediately after the config has been loaded.
            Default to True.
        reload_config: Whether to force reload the config or not, by default if the config has already been loaded
            once it will skip reloading, by setting reload_config to True you ensure that the config will be
            reloaded.

    Raises:
        CriticalSettingException when a critical settings is not defined in local.yml and as env variable.
    """
    config.setup_config(
        app_name=app_name,
        config_path=config_path,
        critical_settings=critical_settings,
        setup_logging=setup_logging,
        reload_config=reload_config,
    )


def setup_unit_test_config(
    app_name: str, config_path: str, config_values: Optional[Dict[str, Dict[str, Any]]] = None
) -> None:
    """Prepare the config object specifically to be used for unit tests.

    Load default.yml and either apply the content
    of unit_test.yaml if it is available and then the environment variables. The content of the param
    config_values will be used as a final overwrite.

    Order of overwrites with unit_test.yml:

        default.yml -> unit_test.yml -> environment variables -> config_values

    Order of overwrites without unit_test.yml:

        default.yml -> environment variables -> config_values

    Args:
        app_name: The name of the application, usually the name of the repo. Ex: my-super-app. This will be
            used for finding the prefix to the environment variables. The name of the app will be uppercased and
            dashes be replaced by underscores.
        config_path: A python path to where the configuration files are. Using python notation for the path and
            starting from the root of the application.
            Ex: tasks.config would mean that the config files are situated in the package config of the package
            tasks from the root of the repo my_task_app.
        config_values: A dictionary mimicking the structure of the config files, to be applied as an overwrite on
            top of default + unit_test config (if available) and env variables.
    """
    config.setup_unit_test_config(app_name=app_name, config_path=config_path, config_values=config_values)


class BaseProcessor(object):
    def __call__(self, logger: logging.Logger, name: str, event_dict: Dict) -> Dict:
        return event_dict


class HostNameProcessor(BaseProcessor):
    def __call__(self, logger: logging.Logger, name: str, event_dict: Dict) -> Dict:
        event_dict["hostname"] = socket.gethostname()
        return event_dict


def load_logging_config(
    custom_processors: Optional[List[BaseProcessor]] = None,
    custom_handlers: Optional[List[Handler]] = None,
    use_hostname_processor: bool = True,
) -> logging.Logger:
    """Load the different logging config parameters as defined in the config of the application.

    Args:
        custom_processors: List of custom processors for log records
        custom_handlers: List of custom handlers to log records
        use_hostname_processor: Use the built-in HostNameProcessor for log records

    Returns:
        A list of handlers depending on the config if argument return_handlers has been set to True.
    """
    if config.logging.disable_processors:
        custom_processors = []
    else:
        custom_processors = custom_processors or []
        if use_hostname_processor:
            custom_processors.append(HostNameProcessor())

    pre_processors = [
        structlog.stdlib.filter_by_level,
    ]
    shared_processors = [
        structlog.stdlib.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.TimeStamper(fmt=config.logging.date_format, utc=config.logging.use_utc),
        structlog.processors.UnicodeDecoder(),
        structlog.stdlib.add_logger_name,
    ] + custom_processors
    post_processors = [structlog.stdlib.ProcessorFormatter.wrap_for_formatter]

    structlog.reset_defaults()
    structlog.configure(
        processors=pre_processors + shared_processors + post_processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
        wrapper_class=structlog.stdlib.BoundLogger,
    )

    use_colors = getattr(config.logging, "colors", False)

    default_level_styles = structlog.dev.ConsoleRenderer.get_default_level_styles(colors=use_colors)

    if use_colors:
        default_level_styles["debug"] = "[34m"  # blue

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.dev.ConsoleRenderer(level_styles=default_level_styles, colors=use_colors),
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

    root_logger.setLevel(config.logging.min_level)

    # Add override for other loggers, usually loggers from libraries
    if hasattr(config.logging, "logger_overrides"):
        for logger_name, min_level in config.logging.logger_overrides.items():
            logging.getLogger(logger_name).setLevel(min_level)

    return root_logger
