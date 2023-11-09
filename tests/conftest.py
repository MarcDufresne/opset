import pytest

from opset import Config


@pytest.fixture(autouse=True, scope="function")
def clean_up_config():
    yield
    Config._config = None
