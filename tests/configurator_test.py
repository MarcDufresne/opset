# configurator_test.py
# Alexandre Jutras, 2018-08-20
# Emilio Assuncao, 2019-01-17
# Marc-Andre Dufresne, 2020-09-10
# Copyright (c) Element AI Inc. All rights not expressly granted hereunder are reserved.

import copy
import logging
import os
import warnings

import pytest
from pytest_mock import MockerFixture
import structlog

from opset import config, load_logging_config, setup_config, setup_unit_test_config
from opset.configurator import Config, CriticalSettingException
from opset.utils import mock_config_file
from tests.utils import clear_env_vars, mock_default_config, mock_gcp_config

TESTING_MODULE = "opset.configurator"


@clear_env_vars
def test_config():
    with mock_config_file(mock_default_config):
        setup_config("fake-tool", "project.config", critical_settings=False, setup_logging=False, reload_config=True)

        assert str(config) == "Config of fake-tool"
        assert config.app.api_key == mock_default_config["app"]["api_key"]


@clear_env_vars
def test_config_local_override():
    local_config = {
        "app": {"values": {"a": 1}},
        "level1": {"level2": {"level3": {"level4": "new value"}}},
    }
    with mock_config_file(mock_default_config, local_config):
        setup_config("fake-tool", "project.config", critical_settings=False, setup_logging=False, reload_config=True)

        assert str(config) == "Config of fake-tool"
        assert config.app.api_key == mock_default_config["app"]["api_key"]
        assert config.level1.level2.level3.level4 == "new value"


def test_config_no_reload():
    with mock_config_file(mock_default_config):
        setup_config("fake-tool", "project.config", critical_settings=False, setup_logging=False, reload_config=True)
        assert str(config) == "Config of fake-tool"
        setup_config("fakez-toolz", "project.config", critical_settings=False, setup_logging=False)
        assert str(config) != "Config of fakez-toolz"


@clear_env_vars
def test_config_env_var_override():
    os.environ["FAKE_TOOL_APP_API_KEY"] = "do_not_override"

    with mock_config_file(mock_default_config):
        setup_config("fake-tool", "project.config", critical_settings=False, setup_logging=False, reload_config=True)
        assert config.app.api_key == "do_not_override"


def test_config_with_logging_config():
    with mock_config_file(mock_default_config):
        setup_config("fake-tool", "project.config", critical_settings=False, setup_logging=True, reload_config=True)

    assert logging.StreamHandler in [type(handler) for handler in logging.getLogger().handlers]


def test_critical_settings():
    with mock_config_file(mock_default_config):
        setup_config("fake-tool", "project.config", critical_settings=False, setup_logging=False, reload_config=True)

    local_config = copy.deepcopy(mock_default_config)
    del local_config["app"]["no_default"]

    with mock_config_file(mock_default_config, local_config):
        with pytest.raises(CriticalSettingException):
            setup_config("fake-tool", "project.config", critical_settings=True, setup_logging=False, reload_config=True)


@clear_env_vars
def test_warn_on_extra_key():
    os.environ["FAKE_TOOL_APP_SOME_UNKNOWN_KEY"] = "unknown"

    with warnings.catch_warnings(record=True) as ws:
        with mock_config_file(mock_default_config, local_values=mock_default_config):
            setup_config(
                "fake-tool", "project.config", critical_settings=False, setup_logging=False, reload_config=True
            )
            assert any(issubclass(w.category, UserWarning) for w in ws)
            warning_messages = [str(w.message) for w in ws]
            assert (
                "Environment variable [FAKE_TOOL_APP_SOME_UNKNOWN_KEY] does not match any "
                "possible setting, ignoring." in warning_messages
            )

    local_config = copy.deepcopy(mock_default_config)
    local_config["app"]["some_unknown_key"] = "unknown"
    with warnings.catch_warnings(record=True) as ws:
        with mock_config_file(mock_default_config, local_config):
            setup_config(
                "fake-tool", "project.config", critical_settings=False, setup_logging=False, reload_config=True
            )
            assert any(issubclass(w.category, UserWarning) for w in ws)
            warning_messages = [str(w.message) for w in ws]
            assert any(
                (
                    warning_message
                    for warning_message in warning_messages
                    if "Override [app.some_unknown_key] not found in base config, ignoring." in warning_message
                )
            )


def test_raise_on_missing_default_file():
    with mock_config_file({}):
        with pytest.raises(FileNotFoundError):
            setup_config(
                "fake-tool", "project.config", critical_settings=False, setup_logging=False, reload_config=True
            )


def test_empty_string_setting():
    with mock_config_file(mock_default_config):
        setup_config("fake-tool", "project.config", critical_settings=False, setup_logging=False, reload_config=True)
        assert config.app.no_default is None, "expected the setting to be None"

    local_config = copy.deepcopy(mock_default_config)
    local_config["app"]["no_default"] = ""
    local_config["app"]["v"] = {"a": 1}
    with mock_config_file(mock_default_config, local_config):
        setup_config("fake-tool", "project.config", critical_settings=True, setup_logging=False, reload_config=True)
        assert config.app.no_default == "", "expected the setting to be overwritten by local.yml to ''"
        assert config.app.v == {"a": 1}, 'expected the setting to be overwritten by local.yml to "{"a": 1}"'

    os.environ["FAKE_TOOL_APP_NO_DEFAULT"] = ""
    os.environ["FAKE_TOOL_APP_V"] = '{"a":1}'
    with mock_config_file(mock_default_config):
        setup_config("fake-tool", "project.config", critical_settings=True, setup_logging=False, reload_config=True)
        assert config.app.no_default == "", "expected the setting to be overwritten by env var to ''"
        assert config.app.v == {"a": 1}, 'expected the setting to be overwritten by env var to "{"a": 1}"'


@clear_env_vars
def test_raise_on_all_missing_variables():
    with mock_config_file({"foo": {"bar": None, "baz": None}}, {}):
        with pytest.raises(CriticalSettingException) as exception_info:
            setup_config("fake-tool", "project.config", critical_settings=True, setup_logging=False, reload_config=True)
            assert all(
                x in exception_info.value.args[0]
                for x in ["section 'foo' and setting 'bar'", "section 'foo' and setting 'baz'"]
            )


def test_load_logging_config():
    with mock_config_file(mock_default_config):
        setup_config("fake-tool", "project.config", critical_settings=False, setup_logging=False, reload_config=True)
        logger = load_logging_config()
        stream_handler = [handler for handler in logger.handlers if type(handler) is logging.StreamHandler][0]
        assert type(stream_handler.formatter) is structlog.stdlib.ProcessorFormatter
        assert type(stream_handler.formatter.processors[1]) is structlog.dev.ConsoleRenderer
        assert logger.level == logging.DEBUG


def test_load_logging_config_with_custom_processor():
    def custom_processor_1(_, __, e):
        return e

    with mock_config_file(mock_default_config):
        setup_config("fake-tool", "project.config", critical_settings=False, setup_logging=False, reload_config=True)
        logger = load_logging_config(custom_processors=[custom_processor_1])
        _handlers = [handler for handler in logger.handlers if type(handler) is logging.StreamHandler]
        stream_handler = _handlers[0]
        assert custom_processor_1 in stream_handler.formatter.foreign_pre_chain


def test_load_logging_config_with_custom_handler():
    class CustomHandler(logging.Handler):
        def __init__(self):
            logging.Handler.__init__(self)

        def emit(self, record):
            print(record)  # noqa: T201

    with mock_config_file(mock_default_config):
        setup_config("fake-tool", "project.config", critical_settings=False, setup_logging=False, reload_config=True)
        logger = load_logging_config(custom_handlers=[CustomHandler()])
        assert len(logger.handlers) == 2
        assert type(logger.handlers[0]) == logging.StreamHandler
        assert type(logger.handlers[1]) == CustomHandler


@clear_env_vars
def test_setup_config_unit_test_with_test_config():
    os.environ["FAKE_TOOL_APP_SECRET_KEY"] = "Quatre-Roue-Force"
    os.environ["FAKE_TOOL_APP_API_KEY"] = "Beton"

    # Test with unit_test.yaml
    with mock_config_file(
        mock_default_config, unit_test_values={"app": {"api_key": "ma clef!"}, "logging": {"disable_processors": True}}
    ):
        setup_unit_test_config("fake_tool", "project.config", config_values={"app": {"secret_key": "pirate!"}})
        assert config.logging.disable_processors is True  # unit_test trumps default
        assert config.app.api_key == "Beton"  # env variables trump unit test
        assert config.app.secret_key == "pirate!"  # values passed during init trump values from env variables


@clear_env_vars
def test_setup_config_unit_test_no_test_config():
    os.environ["FAKE_TOOL_APP_API_KEY"] = "le secret est dans la sauce"
    os.environ["FAKE_TOOL_APP_SECRET_KEY"] = "flibustier!"

    # Test without unit_test.yaml
    with mock_config_file(mock_default_config):
        setup_unit_test_config("fake_tool", "project.config", config_values={"app": {"secret_key": "pirate!"}})
        assert config.app.api_key == "le secret est dans la sauce"  # env variables trump default
        assert config.app.secret_key == "pirate!"  # values passed during init trump values from environment variables


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
        # int
        ("42", 42),
        # float
        ("420.69", 420.69),
        # list
        ("[1, 2, 3]", [1, 2, 3]),
        ('["foo", "bar", true, 0]', ["foo", "bar", True, 0]),
        # dict
        ('{"foo": "bar", "baz": 3000, "bool": false}', {"baz": 3000, "bool": False, "foo": "bar"}),
    ),
)
def test_convert_type(test, expected):
    assert Config._convert_type(test) == expected


@pytest.mark.parametrize("test", ('["test"', "HELLO", "nope", "test2000", '{"test"}'))
def test_convert_type_fallback(test):
    assert Config._convert_type(test) == test


@clear_env_vars
def test_snake_config_section_env_var_override():
    os.environ["FAKE_TOOL_SNAKE_CASE_SECTION_VALUE"] = "new value"
    os.environ["FAKE_TOOL_SNAKE_CASE_SECTION_SPLIT_VALUE"] = "new split value"

    with mock_config_file(mock_default_config), warnings.catch_warnings(record=True) as ws:
        setup_config("fake-tool", "project.config", critical_settings=False, setup_logging=False, reload_config=True)
    assert config.snake_case_section.value == "new value"
    assert config.snake_case_section.split_value == "new split value"

    for w in ws:
        assert "FAKE_TOOL_SNAKE_CASE_SECTION_VALUE" not in str(w.message)
        assert "FAKE_TOOL_SNAKE_CASE_SECTION_SPLIT_VALUE" not in str(w.message)


def test_get_dict_item_from_path():
    d = {"a": {"b": "1"}}
    assert Config._get_dict_item_from_path(d, ["a"]) == {"b": "1"}
    assert Config._get_dict_item_from_path(d, ["a", "b"]) == "1"


def test_json_format() -> None:
    mock_conf = mock_default_config.copy()
    mock_conf["logging"]["json_format"] = True
    with mock_config_file(mock_conf):
        setup_config("fake-tool", "project.config", critical_settings=False, setup_logging=True, reload_config=True)
        root_logger = logging.getLogger()
        assert isinstance(root_logger.handlers[0].formatter.processors[1], structlog.processors.JSONRenderer)



@pytest.fixture()
def mock_retrieve_gcp_secret_value(mocker: MockerFixture):
    return mocker.patch(f"{TESTING_MODULE}.retrieve_gcp_secret_value")


def test_gcp_secret_format(mock_retrieve_gcp_secret_value) -> None:
    fake_secret_value = "Telesto is fun"
    mock_retrieve_gcp_secret_value.return_value = fake_secret_value

    with mock_config_file(mock_gcp_config):
        setup_config("fake-tool", "project.config", critical_settings=False, setup_logging=False, reload_config=True)

        assert str(config) == "Config of fake-tool"
        assert config.secret == fake_secret_value
        assert config.app.api_key == fake_secret_value
        assert config.timeout == mock_gcp_config["timeout"]
