"""Click-based CLI entry point for mcp_forge.

Defines the ``generate`` command and all its options.  All heavy lifting is
delegated to :mod:`mcp_forge.loader`, :mod:`mcp_forge.parser`, and
:mod:`mcp_forge.generator` so this module stays thin and testable.

Typical usage::

    mcp-forge generate path/to/openapi.yaml --language python --output ./my_server
    mcp-forge generate https://api.example.com/openapi.json --language node
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import click

from mcp_forge import __version__


@click.group()
@click.version_option(version=__version__, prog_name="mcp-forge")
def main() -> None:
    """mcp_forge – scaffold an MCP server from an OpenAPI 3.x spec."""


@main.command("generate")
@click.argument("spec", metavar="SPEC")
@click.option(
    "--language",
    "-l",
    type=click.Choice(["python", "node"], case_sensitive=False),
    default="python",
    show_default=True,
    help="Target language for the generated MCP server.",
)
@click.option(
    "--output",
    "-o",
    default="./mcp_server",
    show_default=True,
    help="Output directory for the generated project files.",
    type=click.Path(file_okay=False, dir_okay=True, writable=True, path_type=str),
)
@click.option(
    "--server-name",
    "-n",
    default="",
    help=(
        "Human-readable name for the MCP server. "
        "Defaults to the API title from the spec."
    ),
)
@click.option(
    "--include-auth/--no-auth",
    default=True,
    show_default=True,
    help=(
        "Include authentication boilerplate based on the spec's "
        "securitySchemes (Bearer token / API key)."
    ),
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Print detailed progress information.",
)
def generate(
    spec: str,
    language: str,
    output: str,
    server_name: str,
    include_auth: bool,
    verbose: bool,
) -> None:
    """Generate a fully functional MCP server from an OpenAPI 3.x spec.

    SPEC can be a local file path or a remote URL (http:// or https://).

    Examples:

    \b
        mcp-forge generate openapi.yaml
        mcp-forge generate openapi.yaml --language node --output ./my_node_server
        mcp-forge generate https://api.example.com/openapi.json --language python
        mcp-forge generate openapi.yaml --no-auth --server-name "My Pet API"
    """
    # Defer imports so startup is fast for --help and --version invocations.
    from mcp_forge.generator import GeneratorError, generate as _generate
    from mcp_forge.loader import LoaderError, load_spec
    from mcp_forge.parser import ParserError, parse_spec

    output_dir = Path(output)

    # ------------------------------------------------------------------
    # Step 1: Load the OpenAPI spec.
    # ------------------------------------------------------------------
    _info(f"Loading spec from: {spec}", verbose)
    try:
        spec_dict = load_spec(spec)
    except LoaderError as exc:
        _error(f"Failed to load spec: {exc}")
        sys.exit(1)

    api_title: str = spec_dict.get("info", {}).get("title") or "MCP Server"
    api_version: str = spec_dict.get("info", {}).get("version") or "unknown"
    _info(
        f"Loaded spec: {api_title!r} (version {api_version})",
        verbose,
    )

    # ------------------------------------------------------------------
    # Step 2: Parse operations into ToolDefinitions.
    # ------------------------------------------------------------------
    _info("Parsing operations…", verbose)
    try:
        tool_definitions = parse_spec(spec_dict)
    except ParserError as exc:
        _error(f"Failed to parse spec: {exc}")
        sys.exit(1)

    num_tools = len(tool_definitions)
    if num_tools == 0:
        click.echo(
            click.style(
                "Warning: No operations found in the spec. "
                "The generated server will have no tools.",
                fg="yellow",
            ),
            err=True,
        )
    else:
        _info(f"Found {num_tools} operation(s) to scaffold.", verbose)

    if verbose:
        for tool in tool_definitions:
            click.echo(
                f"  • {tool.http_method:6s} {tool.path}  →  {tool.name}()"
            )

    # ------------------------------------------------------------------
    # Step 3: Generate output files.
    # ------------------------------------------------------------------
    resolved_name = server_name.strip() or api_title
    _info(
        f"Generating {language} MCP server '{resolved_name}' → {output_dir}",
        verbose,
    )
    try:
        written_files = _generate(
            tool_definitions=tool_definitions,
            spec=spec_dict,
            language=language,
            output_dir=output_dir,
            server_name=resolved_name,
            include_auth=include_auth,
        )
    except GeneratorError as exc:
        _error(f"Generation failed: {exc}")
        sys.exit(1)

    # ------------------------------------------------------------------
    # Step 4: Report success.
    # ------------------------------------------------------------------
    click.echo(
        click.style("✓ MCP server scaffolded successfully!", fg="green", bold=True)
    )
    click.echo(f"  Output directory : {output_dir.resolve()}")
    click.echo(f"  Language         : {language}")
    click.echo(f"  Tools generated  : {num_tools}")
    click.echo(f"  Auth boilerplate : {'yes' if include_auth else 'no'}")
    click.echo()
    click.echo("Files written:")
    for path in written_files:
        click.echo(f"  {path}")
    click.echo()
    _print_next_steps(language, output_dir)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _info(message: str, verbose: bool) -> None:
    """Print *message* to stdout only when *verbose* is ``True``.

    Parameters
    ----------
    message:
        Message text to display.
    verbose:
        When ``False`` the message is suppressed.
    """
    if verbose:
        click.echo(message)


def _error(message: str) -> None:
    """Print a styled error *message* to stderr.

    Parameters
    ----------
    message:
        Error message text to display.
    """
    click.echo(
        click.style(f"Error: {message}", fg="red", bold=True),
        err=True,
    )


def _print_next_steps(language: str, output_dir: Path) -> None:
    """Print language-specific next-step instructions to the user.

    Parameters
    ----------
    language:
        The target language (``"python"`` or ``"node"``).
    output_dir:
        The directory where files were written.
    """
    click.echo(click.style("Next steps:", bold=True))
    rel = output_dir

    if language == "python":
        click.echo(f"  cd {rel}")
        click.echo("  python -m venv .venv && source .venv/bin/activate")
        click.echo("  pip install -r requirements.txt")
        click.echo("  export BEARER_TOKEN=<your-token>  # if required")
        click.echo("  python server.py")
    else:  # node
        click.echo(f"  cd {rel}")
        click.echo("  npm install")
        click.echo("  export BEARER_TOKEN=<your-token>  # if required")
        click.echo("  npm start")
