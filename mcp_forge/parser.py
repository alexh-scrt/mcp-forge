"""Parse an OpenAPI 3.x spec dict into a list of ToolDefinition objects.

This module forms the internal contract between the loader and the generator:
it translates raw OpenAPI data structures into the project's canonical
:class:`ToolDefinition` dataclass so that templates remain decoupled from
OpenAPI specifics.

Public API::

    tool_defs = parse_spec(spec_dict)
"""

from __future__ import annotations

from typing import Any


class ParserError(Exception):
    """Raised when the OpenAPI spec cannot be parsed into ToolDefinitions."""


def parse_spec(spec: dict[str, Any]) -> list[Any]:
    """Parse *spec* and return a list of ToolDefinition objects.

    This is a stub implementation that will be fully implemented in Phase 4.
    It returns an empty list so that the scaffold compiles and the CLI runs
    end-to-end without crashing.

    Parameters
    ----------
    spec:
        Parsed OpenAPI 3.x spec dictionary as returned by
        :func:`mcp_forge.loader.load_spec`.

    Returns
    -------
    list[ToolDefinition]
        One entry per discovered OpenAPI operation.

    Raises
    ------
    ParserError
        If the spec structure is too malformed to extract operations from.
    """
    # Full implementation deferred to Phase 4.
    # The data model (ToolDefinition) will be introduced in Phase 2.
    return []
