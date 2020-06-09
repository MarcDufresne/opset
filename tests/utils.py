# utils.py
# Emilio Assuncao, 2019-01-17
# Copyright (c) Element AI Inc. All rights not expressly granted hereunder are reserved.

import os
from functools import wraps


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


mock_default_config = {
    "app": {"api_key": "my_api_key", "secret_key": "my_secret_key", "no_default": None},
    "logging": {
        "date_format": "iso",
        "min_level": "DEBUG",
        "use_utc": "UTC",
        "disable_processors": False,
        "logger_overrides": {"some_3rd_party_lib": "ERROR"},
    },
    "snake_case_section": {"value": 123, "split_value": 111},
}
