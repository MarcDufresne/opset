# __init__.py
# Emilio Assuncao, 2019-01-24
# Copyright (c) Element AI Inc. All rights not expressly granted hereunder are reserved.

from contextlib import contextmanager
from copy import copy
from tempfile import NamedTemporaryFile
from typing import Any, Dict
from unittest.mock import patch

import pkg_resources
import yaml
from munch import Munch  # noqa

from opset.configurator import Config, config


@contextmanager
def mock_config(config_values: Dict[str, Dict[str, Any]]):
    """Inject a fake config into the interpreter.

    This forces the __getattr__ function of the Config singleton object to
    return fake values defined by the config_values parameter. Intended to be used for unit tests, and
    anywhere it is necessary to replace real config values with fake ones.

    This function is more lightweight than fake_config_file in that it does not create a temporary file or necessarily
    mean that a new config object should be setup in order for the config values to take effect.

    Args:
        config_values: config_values: Dict object that contains the key-value pairs for all the variables to be put
            into the fake config object.
    """
    if config:
        temp_config: Config = copy(config)
        temp_config.overwrite_from_dict(config_values)
        temp_config: "Munch" = temp_config._config  # Get Munched config; Config's getattr cause issues with pytest
    else:
        temp_config: Dict = config_values  # If the config hasn't been init, use the config values sent as param

    with patch.object(Config, "__getattr__", side_effect=lambda x: getattr(temp_config, x)):
        yield


@contextmanager
def mock_config_file(
    default_values: Dict, local_values: Dict = None, unit_test_values: Dict = None
) -> NamedTemporaryFile:
    """Spoof a config file by mocking out the return value of pkg_resources.resource_filename().

    To be used as a context manager with the with-as syntax. This function is intended to facilitate unit testing.

    Creates a temporary file and writes some default values to it, and returns said temporary file.

    Args:
        default_values: Dict object that contains the key-value pairs for all the variables to be put into the fake
            default.yml file.
        local_values: Dict object that contains the key-value pairs for all the variables to be put into the fake
            local.yml file.
        unit_test_values: Dict object that contains the key-value pairs for all the variables to be put into the fake
            unit_test.yml file.

    Returns:
        An instance of a TemporaryFile wrapper to be used for replacing the return value of resource_filename. It is
        not necessary to capture this value with _as_ since the config will already be spoofed.
    """
    default_temp_file = NamedTemporaryFile()

    def save_as_tmp(_config, temp_file):
        if not _config:
            return "this-is-not-a-valid-path.yml"
        with open(temp_file.name, "w") as file_buffer:
            yaml.dump(_config, file_buffer)
        return temp_file.name

    configs = {"default.yml": save_as_tmp(default_values, default_temp_file)}

    if local_values:
        local_temp_file = NamedTemporaryFile()
        configs["local.yml"] = save_as_tmp(local_values, local_temp_file)

    if unit_test_values:
        unit_test_temp_file = NamedTemporaryFile()
        configs["unit_test.yml"] = save_as_tmp(unit_test_values, unit_test_temp_file)

    def mock_resource_filename(_, resource):
        return configs.get(resource, "")

    _real_resource_filename = pkg_resources.resource_filename

    try:
        with patch("pkg_resources.resource_filename", mock_resource_filename):
            yield
    finally:
        pkg_resources.resource_filename = _real_resource_filename
