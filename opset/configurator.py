# configurator.py
# Alexandre Jutras, 2018-11-19, Emilio Assuncao, 2019-01-17
# Copyright (c) Element AI Inc. All rights not expressly granted hereunder are reserved.

import json
import logging
import os
import socket
import sys
import warnings
from collections import defaultdict
from functools import partial
from logging import Handler
from typing import Any, Callable, Dict, List, Optional, Union

import pkg_resources
import structlog
import yaml
from munch import Munch, munchify

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

    def __init__(self):
        self.app_name: str = None
        self.config_path: str = None
        self.critical_settings: Dict = {}
        self.setup_logging: bool = True
        self._config: Munch = None

    def __copy__(self):
        raw_config_copy = {}
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

    def __getattr__(self, item):
        try:
            return getattr(self._config, item)
        except AttributeError:
            raise AttributeError(f"Section [{item}] not found in the config.")

    def __str__(self):
        return f"Config of {self.app_name}"

    @property
    def __formatted_name(self) -> Optional[str]:
        """Convert the name of the application to be used as a prefix for fetching environment variables.

        Returns: A representation of the application name fit for fetching environment variables.
        """
        return self.app_name.upper().replace("-", "_") if self.app_name else None

    @staticmethod
    def _convert_type(value: str) -> Union[str, bool, int, float, Dict, List]:
        if value.lower() in ["y", "yes", "t", "true"]:
            return True

        if value.lower() in ["n", "no", "f", "false"]:
            return False

        try:
            value = float(value)
            if value % 1 == 0:
                return int(value)
            return value
        except ValueError:
            pass

        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass

        return value

    def _read_from_env(self, section: str, setting: str, fallback: Callable[[str, str], str]) -> str:
        env_key = f"{self.__formatted_name}_{section.upper()}_{setting.upper()}"
        if env_key in os.environ:
            return self._convert_type(os.environ[env_key])
        return fallback(section, setting)

    def _read_from_dict(
        self, _config: Dict[str, Dict[str, str]], section: str, setting: str, fallback: Callable[[str, str], str]
    ) -> str:
        if section in _config:
            if setting in _config[section]:
                if _config[section][setting] is not None:
                    return _config[section][setting]
        return fallback(section, setting)

    def _get_config_file_path(self, config_name: str) -> str:
        tentative_path = pkg_resources.resource_filename(self.config_path, config_name)

        if not os.path.exists(tentative_path):
            try:
                split_path = self.config_path.rsplit(".", maxsplit=1)
                tentative_path = pkg_resources.resource_filename(split_path[0], f"{split_path[1]}/{config_name}")
            except Exception:
                pass

        return tentative_path

    def _read_yaml_config(self, config_name: str, raise_not_found: bool = True) -> Dict[str, Dict[str, str]]:
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

    def _raise_on_critical_setting(self, *args):
        raise CriticalSettingException()

    def _build_critical_setting_exception(self, missing_settings: List[Dict[str, str]]) -> CriticalSettingException:
        message = ""
        for missing in missing_settings:
            message += f"Missing config for section '{missing['section']}' and setting '{missing['setting']}'. "
        message += (
            f"Please define missing values in "
            f"[{self._get_config_file_path('local.yml')}] or as environment values as "
            f"'{self.__formatted_name}_<SECTION>_<SETTING>'."
        )
        return CriticalSettingException(message)

    def setup_config(
        self,
        app_name: str,
        config_path: str,
        critical_settings: bool = True,
        setup_logging: bool = False,
        reload_config: bool = False,
    ):
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

        declared_settings = default_config = self._read_yaml_config("default.yml", raise_not_found=True)
        local_config = self._read_yaml_config("local.yml", raise_not_found=False)

        # warn if there are environment variables that are not declared in default.yml or if they are malformed
        for key in os.environ.keys():
            if key.startswith(f"{self.__formatted_name}_"):
                try:
                    section, setting = key[len(self.__formatted_name) + 1 :].lower().split("_", maxsplit=1)
                except ValueError:
                    warnings.warn(
                        f"Malformed env variable [{key}], skipping. Make sure the env var name is "
                        f"following this format: {self.__formatted_name}_{{SECTION_NAME}}_{{SETTING_NAME}}"
                    )
                    continue

                if setting not in declared_settings.get(section, {}):
                    warnings.warn(
                        f"Environment variable [{key}] does not match to any known setting "
                        f"in the config for section [{section}] and setting [{setting}]. Ignoring setting."
                    )

        # warn if there is a setting in local.yml not declared in default.yml
        for section_name, section in local_config.items():
            for setting in section:
                if setting not in declared_settings.get(section_name, {}):
                    warnings.warn(
                        f"Setting [{setting}] from section [{section_name}] in the config "
                        f"file [{self._get_config_file_path('local.yml')}] "
                        f"is not in the default config. Ignoring setting."
                    )

        # handling of critical setting flag
        not_found_behaviour = self._raise_on_critical_setting if critical_settings else lambda *args: None

        # set the config settings
        missing_config_stack = []
        for section_name, section in declared_settings.items():
            for setting in section.keys():
                try:
                    self._config[section_name][setting] = self._read_from_env(
                        section_name,
                        setting,
                        fallback=partial(
                            self._read_from_dict,
                            local_config,
                            fallback=partial(self._read_from_dict, default_config, fallback=not_found_behaviour),
                        ),
                    )
                except CriticalSettingException:
                    missing_config_stack.append({"section": section_name, "setting": setting})
        if missing_config_stack:
            raise self._build_critical_setting_exception(missing_config_stack)

        # Cast config to munch so it behaves like an object instead of a dict
        self._config = munchify(self._config)

        if self.setup_logging:
            load_logging_config()

    def setup_unit_test_config(self, app_name: str, config_path: str, config_values: Dict[str, Dict[str, Any]] = None):
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

        logger.info(f"Initializing config for unit tests")

        declared_settings = default_config = self._read_yaml_config("default.yml", raise_not_found=True)
        test_config = self._read_yaml_config("unit_test.yml", raise_not_found=False)

        if test_config:  # Test config available, assuming local dev. default -> unit_test -> env vars -> config_values
            for section_name, section in declared_settings.items():
                for setting in section.keys():
                    self._config[section_name][setting] = self._read_from_dict(
                        config_values,
                        section_name,
                        setting,
                        fallback=partial(
                            self._read_from_env,
                            fallback=partial(
                                self._read_from_dict,
                                test_config,
                                fallback=partial(self._read_from_dict, default_config, fallback=lambda *args: None),
                            ),
                        ),
                    )
        else:  # Test config unavailable or empty, assuming CI/CD. default -> env vars -> config_values
            for section_name, section in declared_settings.items():
                for setting in section.keys():
                    self._config[section_name][setting] = self._read_from_dict(
                        config_values,
                        section_name,
                        setting,
                        fallback=partial(
                            self._read_from_env,
                            fallback=partial(self._read_from_dict, default_config, fallback=lambda *args: None),
                        ),
                    )

        # Cast config to munch so it behaves like an object instead of a dict
        self._config = munchify(self._config)

    def overwrite_from_dict(
        self, config_overwrite: Dict[str, Dict[str, Any]], base_config: Dict[str, Dict[str, Any]] = None
    ):
        """Apply a dictionary structure mimicking the config files to the config, overwriting matching settings.

        Args:
            config_overwrite: A dictionary structure mimicking the config files.
            base_config: The config being overwritten, default to the main config object of Config.
        """
        config_overwrite = config_overwrite or self._config

        for section_name, section in config_overwrite.items():
            for setting in section.keys():
                self._config[section_name][setting] = self._read_from_dict(
                    config_overwrite,
                    section_name,
                    setting,
                    fallback=partial(self._read_from_dict, base_config, fallback=lambda *args: None),
                )


config = Config()


def setup_config(
    app_name: str,
    config_path: str,
    critical_settings: bool = True,
    setup_logging: bool = False,
    reload_config: bool = False,
):
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


def setup_unit_test_config(app_name: str, config_path: str, config_values: Dict[str, Dict[str, Any]] = None):
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
    custom_processors: List[BaseProcessor] = None,
    custom_handlers: List[Handler] = None,
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
