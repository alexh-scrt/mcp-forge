"""Click-based CLI entry point for mcp_forge.

Defines the ``generate`` command and all its options.  All heavy lifting is
delegated to :mod:`mcp_forge.loader`, :mod:`mcp_forge.parser`, and
:mod:`mcp_forge.generator` so this module stays thin and testable.
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
    "output_dir",
    type=click.Path(file_okay=False, dir_okay=True, writable=True, path_type=Path),
    default=Path("mcp_server_output"),
    show_default=True,
    help="Directory where the generated project will be written.",
)
@click.option(
    "--auth/--no-auth",
    default=True,
    show_default=True,
    help="Whether to scaffold authentication boilerplate.",
)
@click.option(
    "--server-name",
    default=None,
    help="Override the MCP server name (defaults to the OpenAPI title).",
)
def generate(
    spec: str,
    language: str,
    output_dir: Path,
    auth: bool,
    server_name: Optional[str],
) -> None:
    """Generate an MCP server from an OpenAPI 3.x SPEC.

    SPEC can be a local file path (YAML or JSON) or a remote HTTPS URL.

    Examples::

        mcp-forge generate ./openapi.yaml
        mcp-forge generate https://example.com/api/openapi.yaml --language node
        mcp-forge generate ./petstore.yaml -o ./my_server --no-auth
    """
    # Imports are deferred to here so that the CLI can be imported without
    # triggering heavy initialisation at import time.
    from mcp_forge.loader import load_spec
    from mcp_forge.parser import parse_spec
    from mcp_forge.generator import generate as run_generate

    click.echo(f"mcp-forge {__version__}")
    click.echo(f"Loading spec from: {spec}")

    try:
        spec_dict = load_spec(spec)
    except Exception as exc:  # noqa: BLE001
        click.secho(f"Error loading spec: {exc}", fg="red", err=True)
        sys.exit(1)

    click.echo("Parsing endpoints…")
    try:
        tool_definitions = parse_spec(spec_dict)
    except Exception as exc:  # noqa: BLE001
        click.secho(f"Error parsing spec: {exc}", fg="red", err=True)
        sys.exit(1)

    click.echo(f"Found {len(tool_definitions)} tool(s).")

    effective_server_name: str = (
        server_name
        or spec_dict.get("info", {}).get("title", "mcp_server")
    )

    click.echo(f"Generating {language} server '{effective_server_name}' → {output_dir}")
    try:
        run_generate(
            tool_definitions=tool_definitions,
            spec=spec_dict,
            language=language.lower(),
            output_dir=output_dir,
            server_name=effective_server_name,
            include_auth=auth,
        )
    except Exception as exc:  # noqa: BLE001
        click.secho(f"Error generating output: {exc}", fg="red", err=True)
        sys.exit(1)

    click.secho("✓ Done!", fg="green")
    click.echo(f"  Output written to: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
