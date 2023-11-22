# utils_test.py
# Alexandre Jutras, 2019-06-26
# Copyright (c) Element AI Inc. All rights not expressly granted hereunder are reserved.

from opset import Config
from opset.utils import mock_config_file
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
