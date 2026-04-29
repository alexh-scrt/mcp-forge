"""mcp_forge – scaffold a fully functional MCP server from any OpenAPI 3.x spec.

This package exposes the public API surface and version string used by the CLI
and by downstream tooling that imports mcp_forge programmatically.

Typical usage::

    from mcp_forge import __version__
    from mcp_forge.loader import load_spec
    from mcp_forge.parser import parse_spec
    from mcp_forge.generator import generate
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
