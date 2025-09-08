import json
import logging
import os
import re
from typing import Any, cast

import google.auth
from google.auth.exceptions import DefaultCredentialsError

from opset import utils

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


class MixedGcpValueTypesError(Exception):
    """Thrown when the values in the secrets are not of the same type"""

    def __init__(self) -> None:
        super().__init__("All secret values must be of the same type to be combined.")


class UnsupportedGcpValueTypesError(Exception):
    """Thrown when the values in the secrets are not of the same type"""

    def __init__(self) -> None:
        super().__init__("Only values of type 'list' or 'dict' can be combined.")


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
    # Cleanup the string a bit to support multiline strings in YAML (e.g. '>-')
    secret_string = secret_string.strip().replace(" ", "")

    _validate_secret_string(secret_string)
    logger.debug(f"Fetching secret from gcp using {secret_string}")
    parsed_secret_names = _parse_unprocessed_gcp_secrets(secret_string)
    project_prefixed_secret_names = _add_project_if_needed(parsed_secret_names)
    versioned_secret_names = _add_version_if_needed(project_prefixed_secret_names)
    fully_processed_secret_names = _apply_project_mapping(versioned_secret_names, config)

    client: secretmanager.SecretManagerServiceClient = OpsetSecretManagerClient.get_or_create()

    gcp_secret_values = []
    try:
        for fully_processed_secret_name in fully_processed_secret_names:
            gcp_secret = client.access_secret_version(
                request=secretmanager.AccessSecretVersionRequest(name=fully_processed_secret_name)
            )
            gcp_secret_values.append(gcp_secret.payload.data.decode("UTF-8"))
    except Exception as e:
        raise GcpError(secret_string) from e

    return _combine_secret_values(gcp_secret_values)


def _apply_project_mapping(secret_names: list[str], config: dict[str, Any] | None = None) -> list[str]:
    if not config or not config.get("gcp_project_mapping"):
        return secret_names

    mapping = cast(dict, config.get("gcp_project_mapping"))

    fixed_secret_names = []
    for secret_name in secret_names:
        tokens = secret_name.split("/")

        mapped_project = mapping.get(tokens[1])
        if mapped_project:
            tokens[1] = mapped_project
            fixed_secret_names.append("/".join(tokens))
        else:
            fixed_secret_names.append(secret_name)

    return fixed_secret_names


def _parse_unprocessed_gcp_secrets(secret_string: str) -> list[str]:
    try:
        path = secret_string.split("//")[1]
        return path.split(";")
    except IndexError:
        raise InvalidGcpSecretStringException(secret_string)


def _validate_secret_string(secret_string: str) -> None:
    """
    Validate the gcp secret string format

    Notes:
        - The string must start with `opset+gcp://`
        - The string must contain one or more secret definitions separated by semicolon
        - Each secret definition must be in one of the following formats:
            1. projects/<project_name>/secrets/<secret_name>/versions/<version>
            2. projects/<project_name>/secrets/<secret_name>
            3. <secret_name>/versions/<version>
            4. <secret_name>
    """
    pattern = r"^opset\+gcp://((projects/[^/]+/secrets/[^/]+(?:/versions/[^/]+)?|[^/]+(?:/versions/[^/]+)?);?)+$"
    match = re.match(pattern, secret_string)

    if not match:
        raise InvalidGcpSecretStringException(secret_string)


def _add_project_if_needed(secret_names: list[str]) -> list[str]:
    """
    Add project prefix to secret names if not already present

    Notes:
        - '<secret_name>/versions/<version>' and '<secret_name>' formats will be prefixed
            with 'projects/{project}/secrets/'
        - 'projects/<project_name>/secrets/<secret_name>/versions/<version>' and
            'projects/<project_name>/secrets/<secret_name>' formats will be left unchanged

    Args:
        secret_names: List of secret names with or without project prefix

    Returns:
        Normalized list of secret names with project prefixes
    """
    project = _get_gcp_project_id() or "default-project"
    project_prefixed_secret_names = []
    for secret_name in secret_names:
        if not secret_name.startswith("projects/"):
            project_prefixed_secret_names.append(f"projects/{project}/secrets/{secret_name}")
        else:
            project_prefixed_secret_names.append(secret_name)

    return project_prefixed_secret_names


def _add_version_if_needed(secret_names: list[str]) -> list[str]:
    versioned_secret_names = []
    for secret_name in secret_names:
        match = re.match(r"^projects/[^/]+?/secrets/[^/]+?(?P<version>/versions/[^/]+?)?$", secret_name)
        if match and not match.groupdict().get("version"):
            versioned_secret_names.append(f"{secret_name}/versions/latest")
        else:
            versioned_secret_names.append(secret_name)

    return versioned_secret_names


def _combine_secret_values(secret_values: list[str]) -> str:
    """
    Combine secret values into a single value

    Notes:
        - If there is only one secret value, return it as is
        - If all secret values are of the same type and are supported types (list or dict), combine
          them into a single merged value

    Args:
        secret_values: list of raw secret values

    Raises:
        UnsupportedGcpValueTypesError: If the values in the secrets are not support (not list or dict)
        MixedGcpValueTypesError: If the values in the secrets are of different types

    Returns:
        Combined secret value, if all secrets are of the same type and are supported types (list or dict)
    """
    if len(secret_values) == 1:
        return secret_values[0]

    converted_values = [utils.convert_type(value) for value in secret_values]
    combined_vals: list[Any] | dict[str, Any]

    if all(isinstance(value, type(converted_values[0])) for value in converted_values):
        if isinstance(converted_values[0], dict):
            dict_vals = cast(list[dict[str, Any]], converted_values)
            combined_vals = {key: value for d in dict_vals for key, value in d.items()}
        elif isinstance(converted_values[0], list):
            list_vals = cast(list[Any], converted_values)
            combined_vals = [value for v in list_vals for value in v]
        else:
            raise UnsupportedGcpValueTypesError()
    else:
        raise MixedGcpValueTypesError()

    return json.dumps(combined_vals)


def _get_gcp_project_id() -> str | None:
    """
    Get the GCP project ID from the metadata server or environment variables

    Notes:
        The project name is taken from the metadata server if available, then from the
        environment variable 'GOOGLE_CLOUD_PROJECT', then `GCP_PROJECT_ID`,
        otherwise returns None.

    Returns:
        Project ID if found, otherwise None
    """
    try:
        _, project_id = google.auth.default()  # type: ignore[no-untyped-call] # https://github.com/googleapis/google-auth-library-python/issues/1543
        if project_id:
            return cast(str, project_id)
    except DefaultCredentialsError:
        pass

    return os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT_ID")
