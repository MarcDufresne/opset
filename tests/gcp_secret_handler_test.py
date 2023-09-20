from unittest.mock import MagicMock

import pytest
from opset.gcp_secret_handler import retrieve_gcp_secret_value, OPSET_GCP_PREFIX, InvalidGcpSecretStringException
from pytest_mock import MockerFixture
from google.cloud import secretmanager

TESTING_MODULE = "opset.gcp_secret_handler"
A_SECRET_VALUE = "photo mark suede"


@pytest.fixture()
def mock_access_secret_version(mocker: MockerFixture):
    mock_client = mocker.patch(f"{TESTING_MODULE}.secretmanager.SecretManagerServiceClient")
    mock_access_secret_version = mocker.MagicMock()
    mock_client.return_value.access_secret_version = mock_access_secret_version

    return mock_access_secret_version


def _mock_gcp_response() -> MagicMock:
    mock_response = MagicMock()
    mock_response.payload.data.decode.return_value = A_SECRET_VALUE

    return mock_response


def test_retrieve_gcp_secret_value(mock_access_secret_version):
    valid_secret_name = f"{OPSET_GCP_PREFIX}projects/test-1991/secrets/reward"
    mock_access_secret_version.return_value = _mock_gcp_response()

    gcp_secret_value = retrieve_gcp_secret_value(valid_secret_name)

    mock_access_secret_version.assert_called_with(
        request=secretmanager.AccessSecretVersionRequest(name="projects/test-1991/secrets/reward/versions/latest")
    )
    assert gcp_secret_value == A_SECRET_VALUE


def test_retrieve_gcp_secret_value_with_specified_version(mock_access_secret_version):
    valid_secret_name = f"{OPSET_GCP_PREFIX}projects/test-1991/secrets/reward/versions/2"
    mock_access_secret_version.return_value = _mock_gcp_response()

    gcp_secret_value = retrieve_gcp_secret_value(valid_secret_name)

    mock_access_secret_version.assert_called_with(
        request=secretmanager.AccessSecretVersionRequest(name="projects/test-1991/secrets/reward/versions/2")
    )
    assert gcp_secret_value == A_SECRET_VALUE

@pytest.mark.parametrize("bad_secret_name", [
    f"{OPSET_GCP_PREFIX}test-1991/secrets/reward",
    f"{OPSET_GCP_PREFIX}",
    f"{OPSET_GCP_PREFIX}reward",
    "bad+prefix://projects/test-1991/secrets/reward",
])
def test_retrieve_gcp_secret_value_with_bad_secret_name(mock_access_secret_version, bad_secret_name):
    mock_access_secret_version.return_value = _mock_gcp_response()

    with pytest.raises(InvalidGcpSecretStringException):
         retrieve_gcp_secret_value(bad_secret_name)

    mock_access_secret_version.assert_not_called()
