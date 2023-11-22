# configurator_test.py
# Alexandre Jutras, 2018-08-20
# Emilio Assuncao, 2019-01-17
# Marc-Andre Dufresne, 2020-09-10
# Copyright (c) Element AI Inc. All rights not expressly granted hereunder are reserved.

import json
import logging
import os
import warnings

import pytest
import structlog
from pydantic import ValidationError
from pytest_mock import MockerFixture

from opset import OpsetSettingsBaseModel
from opset.configurator import Config, OpsetConfigAlreadyInitializedError, get_opset_config, load_logging_config
from opset.utils import mock_config_file
from tests.utils import MockConfig, clear_env_vars, mock_default_config

TESTING_MODULE = "opset.configurator"


@clear_env_vars
def test_config():
    with mock_config_file():
        opset_config = Config("fake-tool", MockConfig, "project.config", setup_logging=False)
        config = opset_config.config

        assert str(opset_config) == "Config of fake-tool"
        assert config.app.api_key == mock_default_config["app"]["api_key"]


@clear_env_vars
def test_config_local_override():
    local_config = {
        "app": {"api_key": "this is from local"},
        "level1": {"level2": {"level3": {"level4": "new value"}}},
    }
    with mock_config_file(local_config):
        opset_config = Config("fake-tool", MockConfig, "project.config", setup_logging=False)
        config = opset_config.config

        assert str(opset_config) == "Config of fake-tool"
        assert config.app.api_key == local_config["app"]["api_key"]
        assert config.level1.level2.level3.level4 == "new value"


def test_config_no_reload():
    with mock_config_file():
        opset_config = Config("fake-tool", MockConfig, "project.config", setup_logging=False)

        assert str(opset_config) == "Config of fake-tool"
        with pytest.raises(OpsetConfigAlreadyInitializedError):
            Config("fakez-toolz", MockConfig, "project.config", setup_logging=False)


@clear_env_vars
def test_config_env_var_override():
    os.environ["FAKE_TOOL_APP_API_KEY"] = "do_not_override"
    os.environ["FAKE_TOOL_TIMEOUT"] = "30"

    with mock_config_file():
        opset_config = Config("fake-tool", MockConfig, "project.config", setup_logging=False)
        assert opset_config.config.app.api_key == "do_not_override"
        assert opset_config.config.timeout == 30


def test_config_with_logging_config():
    with mock_config_file():
        Config("fake-tool", MockConfig, "project.config", setup_logging=True)

    assert logging.StreamHandler in [type(handler) for handler in logging.getLogger().handlers]


@clear_env_vars
def test_warn_on_extra_key():
    os.environ["FAKE_TOOL_APP_SOME_UNKNOWN_KEY"] = "unknown"

    with warnings.catch_warnings(record=True) as ws:
        with mock_config_file(local_values=mock_default_config):
            Config("fake-tool", MockConfig, "project.config", setup_logging=False)
            assert any(issubclass(w.category, UserWarning) for w in ws)
            warning_messages = [str(w.message) for w in ws]
            assert (
                "Environment variable [FAKE_TOOL_APP_SOME_UNKNOWN_KEY] does not match any "
                "possible setting, ignoring." in warning_messages
            )


@clear_env_vars
def test_raise_on_all_missing_variables():
    class Cfg(MockConfig):
        foo: dict[str, str]

    with mock_config_file({"foo": {"bar": None, "baz": None}}, {}):
        with pytest.raises(ValidationError) as exception_info:
            Config("fake-tool", Cfg, "project.config", setup_logging=False)
        assert exception_info.value.error_count() == 2
        assert exception_info.value.errors()[0]["loc"][1] == "bar"
        assert exception_info.value.errors()[1]["loc"][1] == "baz"


def test_load_logging_config():
    with mock_config_file():
        opset_config = Config("fake-tool", MockConfig, "project.config", setup_logging=False)
        logger = load_logging_config(opset_config.config.logging)
        stream_handler = [handler for handler in logger.handlers if type(handler) is logging.StreamHandler][0]
        assert type(stream_handler.formatter) is structlog.stdlib.ProcessorFormatter
        assert type(stream_handler.formatter.processors[1]) is structlog.dev.ConsoleRenderer
        assert logger.level == logging.INFO


def test_load_logging_config_with_custom_processor():
    def custom_processor_1(_, __, e):
        return e

    with mock_config_file(mock_default_config):
        opset_config = Config("fake-tool", MockConfig, "project.config", setup_logging=False)
        logger = load_logging_config(opset_config.config.logging, custom_processors=[custom_processor_1])
        _handlers = [handler for handler in logger.handlers if type(handler) is logging.StreamHandler]
        stream_handler = _handlers[0]
        assert custom_processor_1 in stream_handler.formatter.foreign_pre_chain


def test_load_logging_config_with_custom_handler():
    class CustomHandler(logging.Handler):
        def __init__(self):
            logging.Handler.__init__(self)

        def emit(self, record):
            print(record)  # noqa: T201

    with mock_config_file():
        opset_config = Config("fake-tool", MockConfig, "project.config", setup_logging=False)
        logger = load_logging_config(opset_config.config.logging, custom_handlers=[CustomHandler()])
        assert len(logger.handlers) == 2
        assert type(logger.handlers[0]) == logging.StreamHandler
        assert type(logger.handlers[1]) == CustomHandler


@clear_env_vars
def test_setup_config_unit_test_with_test_config():
    os.environ["FAKE_TOOL_APP_SECRET_KEY"] = "Quatre-Roue-Force"
    os.environ["FAKE_TOOL_APP_API_KEY"] = "Beton"

    # Test with unit_test.yaml
    with mock_config_file(unit_test_values={"app": {"api_key": "ma clef!"}, "logging": {"disable_processors": True}}):
        opset_config = Config(
            "fake_tool",
            MockConfig,
            "project.config",
            config_overrides={
                "app": {"secret_key": "pirate!", "api_key": "ma clef!"},
                "logging": {"disable_processors": True},
            },
        )
        config = opset_config.config
        assert config.logging.disable_processors is True  # unit_test trumps default
        assert config.app.api_key == "ma clef!"  # env variables trump unit test
        assert config.app.secret_key == "pirate!"  # values passed during init trump values from env variables


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
    assert OpsetSettingsBaseModel._convert_type(test) == expected


@pytest.mark.parametrize("test", ('["test"', "HELLO", "nope", "test2000", '{"test"}'))
def test_convert_type_fallback(test):
    assert OpsetSettingsBaseModel._convert_type(test) == test


def test_get_dict_item_from_path():
    d = {"a": {"b": "1"}}
    assert Config._get_dict_item_from_path(d, ["a"]) == {"b": "1"}
    assert Config._get_dict_item_from_path(d, ["a", "b"]) == "1"


def test_setup_unit_test():
    with mock_config_file():
        opset_config = Config("fake-tool", MockConfig, "project.config")

        opset_config.setup_unit_test({"app": {"api_key": "setup unit"}})

        assert opset_config.config.app.api_key == "setup unit"


def test_json_format() -> None:
    mock_conf = mock_default_config.copy()
    mock_conf["logging"]["json_format"] = True
    with mock_config_file(mock_conf):
        Config("fake-tool", MockConfig, "project.config", setup_logging=True)
        root_logger = logging.getLogger()
        assert isinstance(root_logger.handlers[0].formatter.processors[1], structlog.processors.JSONRenderer)


@pytest.fixture()
def mock_retrieve_gcp_secret_value(mocker: MockerFixture):
    return mocker.patch(f"{TESTING_MODULE}.retrieve_gcp_secret_value")


def test_gcp_secret_format(mock_retrieve_gcp_secret_value) -> None:
    fake_secret_value = "Telesto is fun"
    mock_retrieve_gcp_secret_value.return_value = fake_secret_value

    with mock_config_file({"app": {"api_key": "opset+gcp://projects/strickland/secrets/api_key"}}):
        config = Config("fake-tool", MockConfig, "project.config", setup_logging=False).config

        assert config.app.api_key == fake_secret_value


def test_gcp_secret_format_with_json_value(mock_retrieve_gcp_secret_value) -> None:
    fake_secret_value = {"api_key": "dang it bobby", "secret_key": "I sell propane"}
    mock_retrieve_gcp_secret_value.return_value = json.dumps(fake_secret_value)

    with mock_config_file({"app": "opset+gcp://projects/strickland/secrets/app"}):
        config = Config("fake-tool", MockConfig, "project.config", setup_logging=False).config

        assert config.app.secret_key == fake_secret_value["secret_key"]
        assert config.app.api_key == fake_secret_value["api_key"]


def test_get_opset_config(mocker: MockerFixture) -> None:
    mocker.patch(f"{TESTING_MODULE}.os.path.exists", return_true=True)
    mocker.patch("builtins.open")
    mock_yaml = mocker.patch(f"{TESTING_MODULE}.yaml")
    fake_config = mocker.MagicMock()
    fake_config.configure_mock(gcp_project_mapping={"test": "test-1991"})
    mock_yaml.load = mocker.MagicMock(return_value=fake_config)

    opset_config = get_opset_config()

    assert opset_config.gcp_project_mapping == {"test": "test-1991"}


def test_backward_config() -> None:
    from opset.configurator import config

    with mock_config_file():
        Config("fake-tool", MockConfig, "project.config", setup_logging=False)

        assert config.app.api_key == mock_default_config["app"]["api_key"]
