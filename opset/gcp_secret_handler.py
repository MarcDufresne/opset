import logging
from typing import Any


logger = logging.getLogger(__name__)


class InvalidGcpSecretStringException(Exception):
    """Thrown when encounter an invalid gcp secret string."""

    def __init__(self, secret_string: str):
        super().__init__(
            f"Invalid gcp secret value `{secret_string}`. Expected format is `{OPSET_GCP_PREFIX}projects/*/secrets/*`"
        )


try:
    from google.cloud import secretmanager
except ImportError:
    secretmanager = None
    _has_secretmanager = False
else:
    _has_secretmanager = True


OPSET_GCP_PREFIX = "opset+gcp://"


def is_gcp_available() -> bool:
    return _has_secretmanager


def retrieve_gcp_secret_value(secret_string: str) -> Any:
    """Retrieve the secret value from Google cloud secret manager

    :param secret_string: Unprocessed secret value that contains information for secretmanager.
    :return: Value from Google cloud secret manager
    """
    _validate_secret_string(secret_string)
    logger.debug(f"Fetching secret from gcp using {secret_string}")
    parsed_secret_name = _parse_unprocessed_gcp_secret(secret_string)
    secret_name = _add_version_if_needed(parsed_secret_name)

    client = secretmanager.SecretManagerServiceClient()
    gcp_secret = client.access_secret_version(request=secretmanager.AccessSecretVersionRequest(name=secret_name))

    return gcp_secret.payload.data.decode("UTF-8")


def _parse_unprocessed_gcp_secret(secret_string: str) -> str:
    try:
        path = secret_string.split("//")[1]
        return path
    except IndexError:
        raise InvalidGcpSecretStringException(secret_string)


def _validate_secret_string(secret_string: str) -> None:
    try:
        prefix, path = secret_string.split("//")
        tokens = path.split("/")

        if f"{prefix}//" != OPSET_GCP_PREFIX or tokens[0] != "projects" or tokens[2] != "secrets":
            raise InvalidGcpSecretStringException(secret_string)
    except IndexError:
        raise InvalidGcpSecretStringException(secret_string)


def _add_version_if_needed(secret_name: str) -> str:
    if "versions" not in secret_name:
        return f"{secret_name}/versions/latest"

    return secret_name
