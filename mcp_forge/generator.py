"""Orchestrate rendering of Jinja2 templates and write output project files.

This module is the final stage of the mcp_forge pipeline: it receives a list
of :class:`~mcp_forge.models.ToolDefinition` objects together with metadata
from the original spec, selects the correct templates for the requested target
language, renders them, and writes all output files to the chosen directory.

Public API::

    generate(
        tool_definitions=tool_defs,
        spec=spec_dict,
        language="python",
        output_dir=Path("./my_server"),
        server_name="My API Server",
        include_auth=True,
    )
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jinja2 import (
    Environment,
    PackageLoader,
    StrictUndefined,
    TemplateNotFound,
    select_autoescape,
)

from mcp_forge.models import SecurityScheme, ToolDefinition


class GeneratorError(Exception):
    """Raised when output files cannot be rendered or written.

    Always carries a human-readable message suitable for display to the user.
    """


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate(
    *,
    tool_definitions: list[ToolDefinition],
    spec: dict[str, Any],
    language: str,
    output_dir: Path,
    server_name: str = "",
    include_auth: bool = True,
) -> list[Path]:
    """Render Jinja2 templates and write the generated MCP server project.

    Parameters
    ----------
    tool_definitions:
        Parsed tool definitions produced by :func:`mcp_forge.parser.parse_spec`.
    spec:
        The full OpenAPI spec dict (used to extract metadata like the API title
        and base URL when *server_name* is not supplied).
    language:
        Target language – either ``"python"`` or ``"node"``.
    output_dir:
        Directory where the generated files will be written.  Created
        (including parents) if it does not already exist.
    server_name:
        Human-readable server name used in generated comments and the MCP
        server registration.  Defaults to the spec's ``info.title`` value.
    include_auth:
        When ``True``, auth boilerplate (environment-variable reads, header
        injection) is included in the generated server entry point.

    Returns
    -------
    list[Path]
        Absolute paths to every file written to *output_dir*.

    Raises
    ------
    GeneratorError
        If the requested language is unsupported, a template cannot be found,
        rendering fails, or the output directory cannot be created/written to.
    """
    lang = language.lower().strip()
    if lang not in ("python", "node"):
        raise GeneratorError(
            f"Unsupported language {language!r}. Choose 'python' or 'node'."
        )

    # Resolve server_name from the spec when not supplied.
    resolved_server_name = server_name.strip() if server_name.strip() else (
        spec.get("info", {}).get("title") or "MCP Server"
    )

    # Extract the base URL from the first servers entry.
    base_url = _extract_base_url(spec)

    # Collect unique security schemes referenced by any tool.
    security_schemes = _collect_security_schemes(tool_definitions)

    # Build the Jinja2 environment pointed at our bundled templates.
    env = _build_jinja_env()

    # Determine which template files to render for the chosen language.
    template_plan = _get_template_plan(lang)

    # Prepare the template context shared by all templates.
    context: dict[str, Any] = {
        "tools": tool_definitions,
        "server_name": resolved_server_name,
        "base_url": base_url,
        "language": lang,
        "include_auth": include_auth,
        "security_schemes": security_schemes,
        "spec": spec,
    }

    # Create the output directory.
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise GeneratorError(
            f"Cannot create output directory '{output_dir}': {exc}"
        ) from exc

    written: list[Path] = []
    for template_name, output_filename in template_plan:
        rendered = _render_template(env, template_name, context)
        dest = output_dir / output_filename
        _write_file(dest, rendered)
        written.append(dest.resolve())

    return written


# ---------------------------------------------------------------------------
# Template environment
# ---------------------------------------------------------------------------


def _build_jinja_env() -> Environment:
    """Build and return a Jinja2 :class:`~jinja2.Environment`.

    Uses :class:`~jinja2.PackageLoader` to load templates bundled inside the
    ``mcp_forge/templates`` directory, and registers a ``tojson`` filter so
    that templates can serialise Python objects to JSON inline.

    Returns
    -------
    jinja2.Environment
        Configured Jinja2 environment.

    Raises
    ------
    GeneratorError
        If the package template directory cannot be located.
    """
    try:
        loader = PackageLoader("mcp_forge", "templates")
    except ValueError as exc:
        raise GeneratorError(
            f"Cannot locate mcp_forge template directory: {exc}"
        ) from exc

    env = Environment(
        loader=loader,
        autoescape=select_autoescape([]),  # No HTML escaping – we emit code.
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    # Register a tojson filter that templates can use.
    env.filters["tojson"] = _tojson_filter

    return env


def _tojson_filter(value: Any, indent: int | None = None) -> str:
    """Jinja2 filter that serialises *value* to a JSON string.

    Parameters
    ----------
    value:
        Any JSON-serialisable Python object.
    indent:
        Optional indentation level passed to :func:`json.dumps`.

    Returns
    -------
    str
        JSON-encoded string.
    """
    return json.dumps(value, indent=indent, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Template plan
# ---------------------------------------------------------------------------


def _get_template_plan(language: str) -> list[tuple[str, str]]:
    """Return the list of ``(template_path, output_filename)`` pairs for *language*.

    The template path is relative to the ``mcp_forge/templates`` directory and
    is used directly with :meth:`jinja2.Environment.get_template`.

    Parameters
    ----------
    language:
        ``"python"`` or ``"node"``.

    Returns
    -------
    list[tuple[str, str]]
        Ordered list of ``(template_name, output_filename)`` pairs.

    Raises
    ------
    GeneratorError
        If *language* is not recognised.
    """
    plans: dict[str, list[tuple[str, str]]] = {
        "python": [
            ("python/server.py.j2", "server.py"),
            ("python/tools.py.j2", "tools.py"),
            ("python/requirements.txt.j2", "requirements.txt"),
        ],
        "node": [
            ("node/server.js.j2", "server.js"),
            ("node/tools.js.j2", "tools.js"),
            ("node/package.json.j2", "package.json"),
        ],
    }
    if language not in plans:
        raise GeneratorError(
            f"No template plan defined for language {language!r}."
        )
    return plans[language]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _render_template(
    env: Environment,
    template_name: str,
    context: dict[str, Any],
) -> str:
    """Load and render a single Jinja2 template.

    Parameters
    ----------
    env:
        Configured Jinja2 environment.
    template_name:
        Path to the template file relative to the templates root
        (e.g. ``"python/server.py.j2"``)
    context:
        Variables passed to the template.

    Returns
    -------
    str
        Rendered file content.

    Raises
    ------
    GeneratorError
        If the template cannot be found or rendering raises an exception.
    """
    try:
        template = env.get_template(template_name)
    except TemplateNotFound as exc:
        raise GeneratorError(
            f"Template not found: '{template_name}'. "
            "This is likely a packaging issue – ensure mcp_forge was installed correctly."
        ) from exc

    try:
        return template.render(**context)
    except Exception as exc:  # noqa: BLE001
        raise GeneratorError(
            f"Failed to render template '{template_name}': {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# File writing
# ---------------------------------------------------------------------------


def _write_file(dest: Path, content: str) -> None:
    """Write *content* to *dest*, creating parent directories as needed.

    Parameters
    ----------
    dest:
        Destination file path.
    content:
        String content to write (UTF-8 encoded).

    Raises
    ------
    GeneratorError
        If the file cannot be written due to an OS-level error.
    """
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise GeneratorError(
            f"Cannot write file '{dest}': {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_base_url(spec: dict[str, Any]) -> str:
    """Return the base URL from the first ``servers`` entry, or empty string.

    Parameters
    ----------
    spec:
        Full parsed OpenAPI spec dict.

    Returns
    -------
    str
        URL string, e.g. ``"https://api.example.com/v1"``, or ``""``.
    """
    servers: list[Any] = spec.get("servers") or []
    if servers and isinstance(servers[0], dict):
        return servers[0].get("url") or ""
    return ""


def _collect_security_schemes(
    tool_definitions: list[ToolDefinition],
) -> list[SecurityScheme]:
    """Collect unique security schemes from all tool definitions.

    De-duplicates by scheme name and preserves the order in which schemes
    are first encountered.

    Parameters
    ----------
    tool_definitions:
        List of parsed tool definitions.

    Returns
    -------
    list[SecurityScheme]
        Ordered, de-duplicated list of security schemes.
    """
    seen: set[str] = set()
    schemes: list[SecurityScheme] = []
    for tool in tool_definitions:
        for scheme in tool.security_schemes:
            if scheme.name not in seen:
                schemes.append(scheme)
                seen.add(scheme.name)
    return schemes
