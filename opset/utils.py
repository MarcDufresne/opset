# __init__.py
# Emilio Assuncao, 2019-01-24
# Copyright (c) Element AI Inc. All rights not expressly granted hereunder are reserved.
import json
from contextlib import contextmanager
from tempfile import NamedTemporaryFile, _TemporaryFileWrapper  # noqa
from typing import Any, Dict, Generator, Optional, cast
from unittest.mock import patch

import yaml


def convert_type(value: str) -> str | bool | dict | list:
    if value.lower() in ["y", "yes", "t", "true"]:
        return True

    if value.lower() in ["n", "no", "f", "false"]:
        return False

    if isinstance(value, str) and (value.startswith("{") or value.startswith("[")):
        try:
            return cast(dict | list, json.loads(value))
        except json.JSONDecodeError:
            pass

    return value


@contextmanager
def mock_config_file(
    local_values: Optional[Dict] = None,
    unit_test_values: Optional[Dict] = None,
) -> Generator[None, None, None]:
    """Spoof config files by mocking importlib.resources.files().

    To be used as a context manager with the with-as syntax. This function is intended to facilitate unit testing.

    Creates temporary files and writes default values to them, returning said temporary files.

    Args:
        local_values: Dict object that contains the key-value pairs for all the variables to be put into the fake
            local.yml file.
        unit_test_values: Dict object that contains the key-value pairs for all the variables to be put into the fake
            unit_test.yml file.

    Returns:
        A context manager that patches importlib.resources.files to return mock file paths.
    """
    from unittest.mock import MagicMock

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

    def mock_files(package_name: str) -> Any:
        """Create a mock Traversable that supports the / operator."""
        mock_traversable = MagicMock()

        # When divided via /, return the path string from configs or empty string
        mock_traversable.__truediv__ = lambda self, resource_name: configs.get(resource_name, "")
        return mock_traversable

    try:
        with patch("importlib.resources.files", side_effect=mock_files):
            yield
    finally:
        pass
