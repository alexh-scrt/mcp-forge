"""Load and validate an OpenAPI 3.x spec from a local file or remote URL.

Public API::

    spec_dict = load_spec("/path/to/openapi.yaml")
    spec_dict = load_spec("https://example.com/openapi.json")

The returned dict is a plain Python dictionary suitable for passing directly
to :func:`mcp_forge.parser.parse_spec`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import yaml


class LoaderError(Exception):
    """Raised when a spec cannot be loaded or is not valid OpenAPI 3.x."""


def load_spec(source: str) -> dict[str, Any]:
    """Load an OpenAPI 3.x spec from *source* and return it as a dict.

    Parameters
    ----------
    source:
        Either a local filesystem path (absolute or relative) or an ``https://``
        / ``http://`` URL pointing to the raw spec file (YAML or JSON).

    Returns
    -------
    dict[str, Any]
        Parsed spec dictionary.

    Raises
    ------
    LoaderError
        If the file cannot be read, the URL cannot be fetched, the content
        cannot be parsed, or the document does not look like OpenAPI 3.x.
    """
    raw_text = _fetch_raw(source)
    spec = _parse_text(raw_text, source)
    _validate_openapi3(spec, source)
    return spec


def _fetch_raw(source: str) -> str:
    """Return the raw text content of *source*."""
    if source.startswith(("http://", "https://")):
        return _fetch_url(source)
    return _read_file(source)


def _fetch_url(url: str) -> str:
    """Fetch *url* and return its text content.

    Parameters
    ----------
    url:
        The remote URL to fetch.

    Raises
    ------
    LoaderError
        If the HTTP request fails for any reason.
    """
    try:
        response = httpx.get(url, follow_redirects=True, timeout=30.0)
        response.raise_for_status()
        return response.text
    except httpx.HTTPStatusError as exc:
        raise LoaderError(
            f"HTTP {exc.response.status_code} fetching '{url}': {exc}"
        ) from exc
    except httpx.RequestError as exc:
        raise LoaderError(f"Network error fetching '{url}': {exc}") from exc


def _read_file(path_str: str) -> str:
    """Read a local file and return its contents as a string.

    Parameters
    ----------
    path_str:
        Filesystem path to the spec file.

    Raises
    ------
    LoaderError
        If the file does not exist or cannot be read.
    """
    path = Path(path_str)
    if not path.exists():
        raise LoaderError(f"Spec file not found: '{path_str}'")
    if not path.is_file():
        raise LoaderError(f"Path is not a file: '{path_str}'")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise LoaderError(f"Cannot read file '{path_str}': {exc}") from exc


def _parse_text(text: str, source: str) -> dict[str, Any]:
    """Parse *text* as YAML or JSON and return a dict.

    JSON is tried first (cheaper), then YAML.

    Parameters
    ----------
    text:
        Raw string content of the spec.
    source:
        Original source identifier used in error messages.

    Raises
    ------
    LoaderError
        If the content cannot be parsed as either format.
    """
    # Try JSON first – all valid JSON is also valid YAML, but json.loads is
    # faster and produces cleaner errors for JSON-format specs.
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LoaderError(
                f"Failed to parse '{source}' as JSON: {exc}"
            ) from exc
    else:
        try:
            parsed = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise LoaderError(
                f"Failed to parse '{source}' as YAML: {exc}"
            ) from exc

    if not isinstance(parsed, dict):
        raise LoaderError(
            f"Spec '{source}' parsed to {type(parsed).__name__}, expected a mapping."
        )
    return parsed  # type: ignore[return-value]


def _validate_openapi3(spec: dict[str, Any], source: str) -> None:
    """Raise :exc:`LoaderError` if *spec* is not an OpenAPI 3.x document.

    This is a lightweight structural check – it does **not** perform full
    JSON Schema validation of every field, but it confirms the mandatory
    ``openapi`` version key is present and starts with ``"3."``.

    Parameters
    ----------
    spec:
        Parsed spec dictionary.
    source:
        Original source identifier used in error messages.

    Raises
    ------
    LoaderError
        If the document is missing the ``openapi`` key or is not version 3.x.
    """
    version = spec.get("openapi")
    if version is None:
        raise LoaderError(
            f"'{source}' does not contain an 'openapi' version key – "
            "is it an OpenAPI 3.x document?"
        )
    if not isinstance(version, str) or not version.startswith("3."):
        raise LoaderError(
            f"'{source}' declares openapi version '{version}'; "
            "mcp_forge only supports OpenAPI 3.x."
        )
    if "info" not in spec:
        raise LoaderError(
            f"'{source}' is missing the required 'info' object."
        )
    if "paths" not in spec and "components" not in spec:
        raise LoaderError(
            f"'{source}' contains neither 'paths' nor 'components'; "
            "it does not look like a usable OpenAPI spec."
        )
