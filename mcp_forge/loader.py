"""Load and validate an OpenAPI 3.x spec from a local file or remote URL.

This module is responsible for the first stage of the mcp_forge pipeline:
fetching raw content from a filesystem path or HTTPS URL, parsing it as
YAML or JSON, and performing both structural and JSON Schema validation to
ensure the document is a valid OpenAPI 3.x specification before it is
handed off to the parser.

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
import jsonschema
import yaml


# ---------------------------------------------------------------------------
# Minimal JSON Schema for OpenAPI 3.x documents.
# ---------------------------------------------------------------------------
# We validate the required top-level structure rather than pulling in the
# full 2 500-line OpenAPI meta-schema, which would add unnecessary latency.
# This catches the most common mistakes (missing fields, wrong types) while
# remaining fast and dependency-free.
_OPENAPI3_TOP_LEVEL_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "OpenAPI 3.x top-level validation",
    "type": "object",
    "required": ["openapi", "info"],
    "properties": {
        "openapi": {
            "type": "string",
            "pattern": "^3\\.",
            "description": "Must be a 3.x.y version string.",
        },
        "info": {
            "type": "object",
            "required": ["title", "version"],
            "properties": {
                "title": {"type": "string"},
                "version": {"type": "string"},
                "description": {"type": "string"},
                "termsOfService": {"type": "string"},
                "contact": {"type": "object"},
                "license": {"type": "object"},
            },
        },
        "paths": {
            "type": "object",
            "description": "Map of paths to path item objects.",
        },
        "components": {
            "type": "object",
            "description": "Reusable components.",
        },
        "servers": {
            "type": "array",
            "items": {"type": "object"},
        },
        "security": {
            "type": "array",
            "items": {"type": "object"},
        },
        "tags": {
            "type": "array",
            "items": {"type": "object"},
        },
        "externalDocs": {"type": "object"},
    },
    "additionalProperties": True,
}


class LoaderError(Exception):
    """Raised when a spec cannot be loaded, parsed, or validated.

    Callers should catch this exception and present the message to the user;
    it is always a human-readable string explaining the failure.
    """


def load_spec(source: str) -> dict[str, Any]:
    """Load an OpenAPI 3.x spec from *source* and return it as a dict.

    The function performs four steps:

    1. **Fetch** – read the raw text from a local file or remote URL.
    2. **Parse** – decode the text as YAML or JSON.
    3. **Structural validation** – use ``jsonschema`` to verify the required
       top-level OpenAPI fields (``openapi``, ``info.title``,
       ``info.version``).
    4. **Semantic check** – confirm the document has at least a ``paths`` or
       ``components`` section so it is actually useful.

    Parameters
    ----------
    source:
        Either a local filesystem path (absolute or relative) or an
        ``https://`` / ``http://`` URL pointing to the raw spec file
        (YAML or JSON).

    Returns
    -------
    dict[str, Any]
        Fully parsed and validated spec dictionary.

    Raises
    ------
    LoaderError
        If the file cannot be read, the URL cannot be fetched, the content
        cannot be parsed, JSON Schema validation fails, or the document does
        not contain an OpenAPI 3.x version string.
    """
    raw_text = _fetch_raw(source)
    spec = _parse_text(raw_text, source)
    _validate_with_jsonschema(spec, source)
    _validate_semantic(spec, source)
    return spec


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fetch_raw(source: str) -> str:
    """Return the raw text content of *source*.

    Dispatches to :func:`_fetch_url` for HTTP(S) sources and
    :func:`_read_file` for everything else.

    Parameters
    ----------
    source:
        File path or URL string.

    Returns
    -------
    str
        Raw text content.

    Raises
    ------
    LoaderError
        Propagated from the underlying fetch/read helper.
    """
    if source.startswith(("http://", "https://")):
        return _fetch_url(source)
    return _read_file(source)


def _fetch_url(url: str) -> str:
    """Fetch *url* and return its text content.

    Parameters
    ----------
    url:
        The remote URL to fetch.  Both ``http://`` and ``https://`` are
        accepted; redirects are followed automatically.

    Returns
    -------
    str
        Response body decoded as text.

    Raises
    ------
    LoaderError
        If the HTTP request returns a non-2xx status code or if any network
        error occurs (DNS failure, timeout, connection refused, etc.).
    """
    try:
        response = httpx.get(url, follow_redirects=True, timeout=30.0)
        response.raise_for_status()
        return response.text
    except httpx.HTTPStatusError as exc:
        raise LoaderError(
            f"HTTP {exc.response.status_code} fetching '{url}': {exc}"
        ) from exc
    except httpx.TimeoutException as exc:
        raise LoaderError(
            f"Request timed out fetching '{url}': {exc}"
        ) from exc
    except httpx.RequestError as exc:
        raise LoaderError(
            f"Network error fetching '{url}': {exc}"
        ) from exc


def _read_file(path_str: str) -> str:
    """Read a local file and return its contents as a string.

    Parameters
    ----------
    path_str:
        Filesystem path to the spec file (absolute or relative).  Both
        ``.yaml``/``.yml`` and ``.json`` extensions are supported.

    Returns
    -------
    str
        UTF-8 decoded file contents.

    Raises
    ------
    LoaderError
        If the path does not exist, is not a regular file, or cannot be read
        due to OS-level permission or I/O errors.
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

    The heuristic is simple: if the stripped text starts with ``{`` or ``[``
    it is treated as JSON (faster parser, better error messages for JSON
    inputs); otherwise YAML is tried.  All valid JSON is also valid YAML, so
    this ordering is safe.

    Parameters
    ----------
    text:
        Raw string content of the spec.
    source:
        Original source identifier used in error messages.

    Returns
    -------
    dict[str, Any]
        Parsed document as a Python dictionary.

    Raises
    ------
    LoaderError
        If the content cannot be parsed as either JSON or YAML, or if the
        top-level value is not a mapping (dict).
    """
    stripped = text.strip()
    if not stripped:
        raise LoaderError(f"Spec source '{source}' is empty.")

    parsed: Any
    if stripped.startswith("{") or stripped.startswith("["):
        # Looks like JSON – use the faster stdlib parser.
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
            f"Spec '{source}' parsed to {type(parsed).__name__!r}, expected a mapping."
        )
    return parsed  # type: ignore[return-value]


def _validate_with_jsonschema(spec: dict[str, Any], source: str) -> None:
    """Validate *spec* against the OpenAPI 3.x top-level JSON Schema.

    Uses :mod:`jsonschema` with the Draft7Validator.  Only the mandatory
    top-level structure is checked here; full per-operation validation is
    deferred to the parser so that slightly non-conformant but usable specs
    are still processed.

    Parameters
    ----------
    spec:
        Parsed spec dictionary.
    source:
        Original source identifier used in error messages.

    Raises
    ------
    LoaderError
        If any required top-level field is missing or has the wrong type,
        including when the ``openapi`` field does not start with ``"3."``.
    """
    validator = jsonschema.Draft7Validator(_OPENAPI3_TOP_LEVEL_SCHEMA)
    errors = sorted(validator.iter_errors(spec), key=lambda e: list(e.path))
    if errors:
        # Report the first (most significant) error with a friendly message.
        first = errors[0]
        path = " -> ".join(str(p) for p in first.absolute_path) or "(root)"
        raise LoaderError(
            f"OpenAPI spec '{source}' failed schema validation at '{path}': "
            f"{first.message}"
        )


def _validate_semantic(spec: dict[str, Any], source: str) -> None:
    """Perform semantic checks that JSON Schema alone cannot express.

    Currently enforces:

    * The ``openapi`` version string starts with ``"3."`` (belt-and-suspenders
      check since the regex pattern in the JSON Schema already covers this).
    * The document contains at least a ``paths`` or ``components`` key so that
      there is something for the parser to work with.

    Parameters
    ----------
    spec:
        Parsed and JSON-Schema-validated spec dictionary.
    source:
        Original source identifier used in error messages.

    Raises
    ------
    LoaderError
        If the version string is not OpenAPI 3.x, or if neither ``paths``
        nor ``components`` is present in the document.
    """
    version: Any = spec.get("openapi", "")
    if not isinstance(version, str) or not version.startswith("3."):
        raise LoaderError(
            f"'{source}' declares openapi version {version!r}; "
            "mcp_forge only supports OpenAPI 3.x (e.g. '3.0.3', '3.1.0')."
        )

    if "paths" not in spec and "components" not in spec:
        raise LoaderError(
            f"'{source}' contains neither 'paths' nor 'components'; "
            "it does not look like a usable OpenAPI spec."
        )
