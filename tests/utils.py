# utils.py
# Emilio Assuncao, 2019-01-17
# Copyright (c) Element AI Inc. All rights not expressly granted hereunder are reserved.

import os
from functools import wraps
from typing import Any

from opset import OpsetLoggingConfig, OpsetSettingsModel


def remove_env_vars(app_name: str):
    """Remove every environment variables that could interfere with the config.

    Args:
        app_name: The name of the application, needed in order to select only the relevant variables in ENV
    """
    for key in os.environ.keys():
        if key.startswith(app_name):
            del os.environ[key]


def clear_env_vars(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        remove_env_vars("FAKE_TOOL")

        try:
            result = fn(*args, **kwargs)
        finally:
            remove_env_vars("FAKE_TOOL")

        return result

    return wrapper


class MockAppConfig(OpsetSettingsModel):
    api_key: str = "my_api_key"
    secret_key: str = "my_secret_key"
    no_default: str | None = None
    v: str | None = None
    d: dict[str, Any] = {}


class Mocklevel3Config(OpsetSettingsModel):
    level4: str = "value"


class MockLevel2Config(OpsetSettingsModel):
    level3: Mocklevel3Config


class MockLevel1Config(OpsetSettingsModel):
    level2: MockLevel2Config = MockLevel2Config()


class MockConfig(OpsetSettingsModel):
    timeout: int = 20
    app: MockAppConfig
    logging: OpsetLoggingConfig
    level1: MockLevel1Config


mock_default_config = MockConfig().model_dump()
