"""Smoke tests for the Phase 1 scaffold.

Verifies that all public modules import correctly and that the basic CLI
entry point is wired up, without exercising any real business logic.
"""

from __future__ import annotations

import importlib

import pytest
from click.testing import CliRunner


def test_package_imports() -> None:
    """All top-level modules must be importable without errors."""
    for module_name in [
        "mcp_forge",
        "mcp_forge.cli",
        "mcp_forge.loader",
        "mcp_forge.parser",
        "mcp_forge.generator",
    ]:
        mod = importlib.import_module(module_name)
        assert mod is not None, f"{module_name} failed to import"


def test_version_string() -> None:
    """__version__ must be a non-empty string."""
    from mcp_forge import __version__

    assert isinstance(__version__, str)
    assert len(__version__) > 0


def test_cli_help() -> None:
    """'mcp-forge --help' must exit 0 and print usage information."""
    from mcp_forge.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Usage" in result.output


def test_cli_version() -> None:
    """'mcp-forge --version' must display the package version."""
    from mcp_forge import __version__
    from mcp_forge.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_generate_help() -> None:
    """'mcp-forge generate --help' must list all expected options."""
    from mcp_forge.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["generate", "--help"])
    assert result.exit_code == 0
    for flag in ["--language", "--output", "--auth", "--server-name"]:
        assert flag in result.output, f"Expected flag '{flag}' in help output"


def test_loader_error_on_missing_file() -> None:
    """load_spec must raise LoaderError for a non-existent file path."""
    from mcp_forge.loader import LoaderError, load_spec

    with pytest.raises(LoaderError, match="not found"):
        load_spec("/non/existent/path/openapi.yaml")


def test_parser_returns_list() -> None:
    """parse_spec stub must return a list (empty for now)."""
    from mcp_forge.parser import parse_spec

    # Minimal valid-looking spec dict
    result = parse_spec({"openapi": "3.0.0", "info": {"title": "Test"}, "paths": {}})
    assert isinstance(result, list)


def test_generator_rejects_bad_language() -> None:
    """generate must raise GeneratorError for unknown languages."""
    from pathlib import Path

    from mcp_forge.generator import GeneratorError, generate

    with pytest.raises(GeneratorError, match="Unsupported language"):
        generate(
            tool_definitions=[],
            spec={},
            language="ruby",
            output_dir=Path("/tmp/test_output"),
            server_name="test",
        )


def test_generator_creates_output_dir(tmp_path: Path) -> None:
    """generate must create the output directory when it does not exist."""
    from mcp_forge.generator import generate

    out = tmp_path / "new_server"
    assert not out.exists()
    generate(
        tool_definitions=[],
        spec={},
        language="python",
        output_dir=out,
        server_name="test",
    )
    assert out.exists()
    assert out.is_dir()
