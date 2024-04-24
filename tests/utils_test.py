# utils_test.py
# Alexandre Jutras, 2019-06-26
# Copyright (c) Element AI Inc. All rights not expressly granted hereunder are reserved.
import pytest

from opset import Config
from opset.utils import convert_type, mock_config_file
from tests.utils import MockConfig, mock_default_config


def test_mock_config():
    overwrite_api_key_value = "bin kin mon coquin toi"

    # Setup config
    with mock_config_file():
        opset_config = Config("fake-tool", MockConfig, "project.config", setup_logging=True)
        config = opset_config.config

    def external_function():
        return config.app.api_key

    # Verifying that mock_config will change the value of config.app.api_key
    with config.opset.mock_config({"app": {"api_key": overwrite_api_key_value}}):
        assert external_function() == overwrite_api_key_value

    # Verifying that the original value is in config.app.api_key
    assert config.app.api_key == mock_default_config["app"]["api_key"]


@pytest.mark.parametrize(
    "test, expected",
    (
        # str
        ("foo", "foo"),
        ("BAR", "BAR"),
        # bool
        ("true", True),
        ("TRUE", True),
        ("t", True),
        ("yes", True),
        ("y", True),
        ("false", False),
        ("f", False),
        ("no", False),
        ("n", False),
        # list
        ("[1, 2, 3]", [1, 2, 3]),
        ('["foo", "bar", true, 0]', ["foo", "bar", True, 0]),
        # dict
        ('{"foo": "bar", "baz": 3000, "bool": false}', {"baz": 3000, "bool": False, "foo": "bar"}),
    ),
)
def test_convert_type(test, expected):
    assert convert_type(test) == expected


@pytest.mark.parametrize("test", ('["test"', "HELLO", "nope", "test2000", '{"test"}'))
def test_convert_type_fallback(test):
    assert convert_type(test) == test
