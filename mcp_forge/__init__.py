"""mcp_forge – scaffold a fully functional MCP server from any OpenAPI 3.x spec.

This package exposes the public API surface and version string used by the CLI
and by downstream tooling that imports mcp_forge programmatically.

Typical usage::

    from mcp_forge import __version__
    from mcp_forge.loader import load_spec
    from mcp_forge.parser import parse_spec
    from mcp_forge.generator import generate

Pipeline overview::

    spec_dict      = load_spec("path/to/openapi.yaml")   # loader.py
    tool_defs      = parse_spec(spec_dict)                # parser.py
    written_files  = generate(                            # generator.py
        tool_definitions=tool_defs,
        spec=spec_dict,
        language="python",
        output_dir=Path("./my_server"),
    )
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = [
    "__version__",
]
