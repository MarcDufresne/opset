# utils_test.py
# Alexandre Jutras, 2019-06-26
# Copyright (c) Element AI Inc. All rights not expressly granted hereunder are reserved.

from opset import config, setup_config
from opset.utils import mock_config, mock_config_file
from tests.utils import mock_default_config


def test_mock_config():

    overwrite_api_key_value = "bin kin mon coquin toi"

    def external_function():
        return config.app.api_key

    # Setup config
    with mock_config_file(mock_default_config):
        setup_config('fake-tool', 'project.config', critical_settings=False, setup_logging=True, reload_config=True)

    # Verifying that the original value is in config.app.api_key
    assert config.app.api_key == mock_default_config["app"]["api_key"]

    # Verifying that mock_config will change the value of config.app.api_key
    with mock_config({"app": {"api_key": overwrite_api_key_value}}):
        assert external_function() == overwrite_api_key_value
