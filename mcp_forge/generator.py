"""Orchestrate rendering of Jinja2 templates and write output project files.

This module is the final stage of the pipeline: it receives a list of
:class:`~mcp_forge.parser.ToolDefinition` objects together with metadata from
the original spec, selects the correct templates for the requested target
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

from pathlib import Path
from typing import Any


class GeneratorError(Exception):
    """Raised when output files cannot be rendered or written."""


def generate(
    tool_definitions: list[Any],
    spec: dict[str, Any],
    language: str,
    output_dir: Path,
    server_name: str,
    include_auth: bool = True,
) -> None:
    """Render templates for *language* and write the output project to *output_dir*.

    This is a stub implementation that will be fully realised in Phase 6.
    It creates the output directory so that the scaffold's end-to-end path
    (CLI → loader → parser → generator) works without error.

    Parameters
    ----------
    tool_definitions:
        List of :class:`~mcp_forge.parser.ToolDefinition` objects produced by
        :func:`mcp_forge.parser.parse_spec`.
    spec:
        Original parsed OpenAPI spec dict (used for metadata such as base URL
        and security schemes).
    language:
        ``"python"`` or ``"node"``.
    output_dir:
        Directory into which all generated files will be written.  Created if
        it does not already exist.
    server_name:
        Human-readable name used as the MCP server identifier in templates.
    include_auth:
        When ``True``, authentication boilerplate is rendered into the output.

    Raises
    ------
    GeneratorError
        If an unsupported language is requested or files cannot be written.
    """
    if language not in ("python", "node"):
        raise GeneratorError(
            f"Unsupported language '{language}'. Choose 'python' or 'node'."
        )

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise GeneratorError(
            f"Cannot create output directory '{output_dir}': {exc}"
        ) from exc

    # Full rendering logic deferred to Phase 6 (requires Phase 5 templates
    # and Phase 2 ToolDefinition model).
