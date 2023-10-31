import logging
import re
from typing import Any, cast

try:
    from google.cloud import secretmanager
except ImportError:
    secretmanager = None  # type: ignore
    _has_secretmanager = False
else:
    _has_secretmanager = True

OPSET_GCP_PREFIX = "opset+gcp://"

logger = logging.getLogger(__name__)


class InvalidGcpSecretStringException(Exception):
    """Thrown when encounter an invalid gcp secret string."""

    def __init__(self, secret_string: str) -> None:
        super().__init__(
            f"Invalid gcp secret value `{secret_string}`. Expected format is `{OPSET_GCP_PREFIX}projects/*/secrets/*`"
        )


class MissingGcpSecretManagerLibrary(Exception):
    """Thrown when a gcp string are detected without the Google cloud secret manager package installed"""

    def __init__(self) -> None:
        super().__init__(
            f"Extra [gcp] not installed. However values starting with {OPSET_GCP_PREFIX} are present in the config."
        )


class GcpError(Exception):
    """Thrown when the communication with google cloud return an error"""

    def __init__(self, secret_string: str):
        super().__init__(f"Got error from google cloud secret manager API for secret `{secret_string}`.")


def is_gcp_available() -> bool:
    return _has_secretmanager


class OpsetSecretManagerClient:
    instance: Any | None = None

    @classmethod
    def get_or_create(cls) -> Any:
        if not cls.instance:
            cls.instance = secretmanager.SecretManagerServiceClient()

        return cls.instance


def retrieve_gcp_secret_value(secret_string: str, config: dict[str, Any] | None = None) -> str:
    """Retrieve the secret value from Google cloud secret manager

    Args:
        secret_string: Unprocessed secret value that contains information for secretmanager.
        config: Opset Gcp config that contains mapping

    Returns:
        Value from Google cloud secret manager
    """
    _validate_secret_string(secret_string)
    logger.debug(f"Fetching secret from gcp using {secret_string}")
    parsed_secret_name = _parse_unprocessed_gcp_secret(secret_string)
    versioned_secret_name = _add_version_if_needed(parsed_secret_name)
    fully_processed_secret_name = _apply_project_mapping(versioned_secret_name, config)

    client: secretmanager.SecretManagerServiceClient = OpsetSecretManagerClient.get_or_create()

    try:
        gcp_secret = client.access_secret_version(
            request=secretmanager.AccessSecretVersionRequest(name=fully_processed_secret_name)
        )

        return gcp_secret.payload.data.decode("UTF-8")
    except Exception as e:
        raise GcpError(secret_string) from e


def _apply_project_mapping(secret_name: str, config: dict[str, Any] | None = None) -> str:
    if config and config.get("gcp_project_mapping"):
        tokens = secret_name.split("/")

        mapped_project = cast(dict, config.get("gcp_project_mapping")).get(tokens[1])
        if mapped_project:
            tokens[1] = mapped_project
            return "/".join(tokens)

    return secret_name


def _parse_unprocessed_gcp_secret(secret_string: str) -> str:
    try:
        path = secret_string.split("//")[1]
        return path
    except IndexError:
        raise InvalidGcpSecretStringException(secret_string)


def _validate_secret_string(secret_string: str) -> None:
    match = re.match(r"^opset\+gcp://projects/.+?/secrets/[^/]+?(?P<version>/versions/[^/]+?)?$", secret_string)

    if not match:
        raise InvalidGcpSecretStringException(secret_string)


def _add_version_if_needed(secret_name: str) -> str:
    match = re.match(r"^projects/.+?/secrets/[^/]+?(?P<version>/versions/[^/]+?)?$", secret_name)
    if match and not match.groupdict().get("version"):
        return f"{secret_name}/versions/latest"

    return secret_name
