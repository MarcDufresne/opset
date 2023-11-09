# __init__.py
# Emilio Assuncao, 2019-01-24
# Copyright (c) Element AI Inc. All rights not expressly granted hereunder are reserved.

from contextlib import contextmanager
from tempfile import NamedTemporaryFile, _TemporaryFileWrapper  # noqa
from typing import Any, Dict, Generator, Optional
from unittest.mock import patch

import pkg_resources
import yaml


@contextmanager
def mock_config_file(
    local_values: Optional[Dict] = None,
    unit_test_values: Optional[Dict] = None,
) -> Generator[None, None, None]:
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

    def save_as_tmp(_config: Dict[str, Dict[str, Any]], temp_file: _TemporaryFileWrapper) -> str:
        if not _config:
            return "this-is-not-a-valid-path.yml"
        with open(temp_file.name, "w") as file_buffer:
            yaml.dump(_config, file_buffer)
        return temp_file.name

    configs = {}

    if local_values:
        local_temp_file = NamedTemporaryFile()
        configs["local.yml"] = save_as_tmp(local_values, local_temp_file)

    if unit_test_values:
        unit_test_temp_file = NamedTemporaryFile()
        configs["unit_test.yml"] = save_as_tmp(unit_test_values, unit_test_temp_file)

    def mock_resource_filename(_: Any, resource: str) -> Any:
        return configs.get(resource, "")

    _real_resource_filename = pkg_resources.resource_filename

    try:
        with patch("pkg_resources.resource_filename", mock_resource_filename):
            yield
    finally:
        pkg_resources.resource_filename = _real_resource_filename
