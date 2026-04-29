"""Tests for mcp_forge.generator.

Covers template rendering, file writing, language selection, auth boilerplate,
and error handling in the generator module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from mcp_forge.generator import (
    GeneratorError,
    _collect_security_schemes,
    _extract_base_url,
    _get_template_plan,
    _render_template,
    _write_file,
    generate,
    _build_jinja_env,
)
from mcp_forge.models import (
    ParameterLocation,
    RequestBody,
    RequestBodyField,
    SecurityScheme,
    SecuritySchemeType,
    ToolDefinition,
    ToolParameter,
)
from mcp_forge.parser import parse_spec

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).parent / "fixtures"
PETSTORE_YAML = FIXTURE_DIR / "petstore.yaml"


def _load_petstore() -> dict[str, Any]:
    """Load the petstore YAML fixture."""
    return yaml.safe_load(PETSTORE_YAML.read_text(encoding="utf-8"))


def _minimal_tool(
    name: str = "list_items",
    method: str = "GET",
    path: str = "/items",
    description: str = "List items.",
) -> ToolDefinition:
    """Return a minimal ToolDefinition for testing."""
    return ToolDefinition(
        name=name,
        description=description,
        http_method=method,
        path=path,
        parameters=[],
        request_body=None,
        security_schemes=[],
        tags=[],
        operation_id=name,
        response_schema={},
        base_url="https://api.example.com",
        deprecated=False,
    )


def _bearer_scheme() -> SecurityScheme:
    """Return a bearer auth security scheme."""
    return SecurityScheme(
        name="bearerAuth",
        scheme_type=SecuritySchemeType.HTTP,
        http_scheme="bearer",
        bearer_format="JWT",
        description="JWT Bearer",
    )


def _api_key_scheme() -> SecurityScheme:
    """Return an API key security scheme."""
    return SecurityScheme(
        name="apiKey",
        scheme_type=SecuritySchemeType.API_KEY,
        api_key_in="header",
        api_key_name="X-API-Key",
        description="API key",
    )


def _minimal_spec(**extra: Any) -> dict[str, Any]:
    """Return a minimal OpenAPI spec dict."""
    spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {},
    }
    spec.update(extra)
    return spec


# ---------------------------------------------------------------------------
# generate() – Python target
# ---------------------------------------------------------------------------


class TestGeneratePython:
    """Integration tests for the Python code generator."""

    def test_creates_output_directory(self, tmp_path: Path) -> None:
        out = tmp_path / "new_server"
        assert not out.exists()
        generate(
            tool_definitions=[_minimal_tool()],
            spec=_minimal_spec(),
            language="python",
            output_dir=out,
        )
        assert out.is_dir()

    def test_writes_three_files(self, tmp_path: Path) -> None:
        out = tmp_path / "server"
        written = generate(
            tool_definitions=[_minimal_tool()],
            spec=_minimal_spec(),
            language="python",
            output_dir=out,
        )
        assert len(written) == 3

    def test_server_py_created(self, tmp_path: Path) -> None:
        out = tmp_path / "server"
        generate(
            tool_definitions=[_minimal_tool()],
            spec=_minimal_spec(),
            language="python",
            output_dir=out,
        )
        assert (out / "server.py").is_file()

    def test_tools_py_created(self, tmp_path: Path) -> None:
        out = tmp_path / "server"
        generate(
            tool_definitions=[_minimal_tool()],
            spec=_minimal_spec(),
            language="python",
            output_dir=out,
        )
        assert (out / "tools.py").is_file()

    def test_requirements_txt_created(self, tmp_path: Path) -> None:
        out = tmp_path / "server"
        generate(
            tool_definitions=[_minimal_tool()],
            spec=_minimal_spec(),
            language="python",
            output_dir=out,
        )
        assert (out / "requirements.txt").is_file()

    def test_server_py_contains_tool_name(self, tmp_path: Path) -> None:
        out = tmp_path / "server"
        generate(
            tool_definitions=[_minimal_tool(name="list_items")],
            spec=_minimal_spec(),
            language="python",
            output_dir=out,
        )
        content = (out / "server.py").read_text(encoding="utf-8")
        assert "list_items" in content

    def test_tools_py_contains_async_function(self, tmp_path: Path) -> None:
        out = tmp_path / "server"
        generate(
            tool_definitions=[_minimal_tool(name="my_tool")],
            spec=_minimal_spec(),
            language="python",
            output_dir=out,
        )
        content = (out / "tools.py").read_text(encoding="utf-8")
        assert "async def my_tool" in content

    def test_tools_py_contains_tool_definitions_list(self, tmp_path: Path) -> None:
        out = tmp_path / "server"
        generate(
            tool_definitions=[_minimal_tool()],
            spec=_minimal_spec(),
            language="python",
            output_dir=out,
        )
        content = (out / "tools.py").read_text(encoding="utf-8")
        assert "TOOL_DEFINITIONS" in content

    def test_requirements_txt_contains_mcp(self, tmp_path: Path) -> None:
        out = tmp_path / "server"
        generate(
            tool_definitions=[],
            spec=_minimal_spec(),
            language="python",
            output_dir=out,
        )
        content = (out / "requirements.txt").read_text(encoding="utf-8")
        assert "mcp" in content

    def test_server_name_in_server_py(self, tmp_path: Path) -> None:
        out = tmp_path / "server"
        generate(
            tool_definitions=[_minimal_tool()],
            spec=_minimal_spec(),
            language="python",
            output_dir=out,
            server_name="My Pet API",
        )
        content = (out / "server.py").read_text(encoding="utf-8")
        assert "My Pet API" in content

    def test_server_name_defaults_to_spec_title(self, tmp_path: Path) -> None:
        spec = _minimal_spec()
        spec["info"]["title"] = "Awesome API"
        out = tmp_path / "server"
        generate(
            tool_definitions=[_minimal_tool()],
            spec=spec,
            language="python",
            output_dir=out,
        )
        content = (out / "server.py").read_text(encoding="utf-8")
        assert "Awesome API" in content

    def test_base_url_in_server_py(self, tmp_path: Path) -> None:
        spec = _minimal_spec(servers=[{"url": "https://api.example.com/v1"}])
        out = tmp_path / "server"
        generate(
            tool_definitions=[_minimal_tool()],
            spec=spec,
            language="python",
            output_dir=out,
        )
        content = (out / "server.py").read_text(encoding="utf-8")
        assert "https://api.example.com/v1" in content

    def test_bearer_auth_included_when_include_auth_true(self, tmp_path: Path) -> None:
        tool = _minimal_tool()
        tool.security_schemes.append(_bearer_scheme())
        out = tmp_path / "server"
        generate(
            tool_definitions=[tool],
            spec=_minimal_spec(),
            language="python",
            output_dir=out,
            include_auth=True,
        )
        content = (out / "server.py").read_text(encoding="utf-8")
        assert "BEARER_TOKEN" in content

    def test_auth_not_included_when_include_auth_false(self, tmp_path: Path) -> None:
        tool = _minimal_tool()
        tool.security_schemes.append(_bearer_scheme())
        out = tmp_path / "server"
        generate(
            tool_definitions=[tool],
            spec=_minimal_spec(),
            language="python",
            output_dir=out,
            include_auth=False,
        )
        content = (out / "server.py").read_text(encoding="utf-8")
        assert "BEARER_TOKEN" not in content

    def test_http_method_in_tools_py(self, tmp_path: Path) -> None:
        out = tmp_path / "server"
        generate(
            tool_definitions=[_minimal_tool(method="POST", name="create_item")],
            spec=_minimal_spec(),
            language="python",
            output_dir=out,
        )
        content = (out / "tools.py").read_text(encoding="utf-8")
        assert "post" in content.lower()

    def test_path_in_tools_py(self, tmp_path: Path) -> None:
        out = tmp_path / "server"
        generate(
            tool_definitions=[_minimal_tool(path="/widgets/{id}")],
            spec=_minimal_spec(),
            language="python",
            output_dir=out,
        )
        content = (out / "tools.py").read_text(encoding="utf-8")
        assert "/widgets/{id}" in content

    def test_multiple_tools_all_in_tools_py(self, tmp_path: Path) -> None:
        tools = [
            _minimal_tool(name="list_pets", path="/pets"),
            _minimal_tool(name="create_pet", method="POST", path="/pets"),
            _minimal_tool(name="get_pet", path="/pets/{id}"),
        ]
        out = tmp_path / "server"
        generate(
            tool_definitions=tools,
            spec=_minimal_spec(),
            language="python",
            output_dir=out,
        )
        content = (out / "tools.py").read_text(encoding="utf-8")
        assert "list_pets" in content
        assert "create_pet" in content
        assert "get_pet" in content

    def test_returns_list_of_paths(self, tmp_path: Path) -> None:
        out = tmp_path / "server"
        result = generate(
            tool_definitions=[_minimal_tool()],
            spec=_minimal_spec(),
            language="python",
            output_dir=out,
        )
        assert isinstance(result, list)
        assert all(isinstance(p, Path) for p in result)


# ---------------------------------------------------------------------------
# generate() – Node.js target
# ---------------------------------------------------------------------------


class TestGenerateNode:
    """Integration tests for the Node.js code generator."""

    def test_writes_three_files(self, tmp_path: Path) -> None:
        out = tmp_path / "server"
        written = generate(
            tool_definitions=[_minimal_tool()],
            spec=_minimal_spec(),
            language="node",
            output_dir=out,
        )
        assert len(written) == 3

    def test_server_js_created(self, tmp_path: Path) -> None:
        out = tmp_path / "server"
        generate(
            tool_definitions=[_minimal_tool()],
            spec=_minimal_spec(),
            language="node",
            output_dir=out,
        )
        assert (out / "server.js").is_file()

    def test_tools_js_created(self, tmp_path: Path) -> None:
        out = tmp_path / "server"
        generate(
            tool_definitions=[_minimal_tool()],
            spec=_minimal_spec(),
            language="node",
            output_dir=out,
        )
        assert (out / "tools.js").is_file()

    def test_package_json_created(self, tmp_path: Path) -> None:
        out = tmp_path / "server"
        generate(
            tool_definitions=[_minimal_tool()],
            spec=_minimal_spec(),
            language="node",
            output_dir=out,
        )
        assert (out / "package.json").is_file()

    def test_server_js_contains_tool_name(self, tmp_path: Path) -> None:
        out = tmp_path / "server"
        generate(
            tool_definitions=[_minimal_tool(name="list_items")],
            spec=_minimal_spec(),
            language="node",
            output_dir=out,
        )
        content = (out / "server.js").read_text(encoding="utf-8")
        assert "list_items" in content

    def test_tools_js_contains_async_function(self, tmp_path: Path) -> None:
        out = tmp_path / "server"
        generate(
            tool_definitions=[_minimal_tool(name="my_tool")],
            spec=_minimal_spec(),
            language="node",
            output_dir=out,
        )
        content = (out / "tools.js").read_text(encoding="utf-8")
        assert "async function my_tool" in content

    def test_package_json_contains_sdk_dependency(self, tmp_path: Path) -> None:
        out = tmp_path / "server"
        generate(
            tool_definitions=[],
            spec=_minimal_spec(),
            language="node",
            output_dir=out,
        )
        content = (out / "package.json").read_text(encoding="utf-8")
        assert "@modelcontextprotocol/sdk" in content

    def test_bearer_auth_in_server_js(self, tmp_path: Path) -> None:
        tool = _minimal_tool()
        tool.security_schemes.append(_bearer_scheme())
        out = tmp_path / "server"
        generate(
            tool_definitions=[tool],
            spec=_minimal_spec(),
            language="node",
            output_dir=out,
            include_auth=True,
        )
        content = (out / "server.js").read_text(encoding="utf-8")
        assert "BEARER_TOKEN" in content

    def test_no_auth_not_in_server_js(self, tmp_path: Path) -> None:
        tool = _minimal_tool()
        tool.security_schemes.append(_bearer_scheme())
        out = tmp_path / "server"
        generate(
            tool_definitions=[tool],
            spec=_minimal_spec(),
            language="node",
            output_dir=out,
            include_auth=False,
        )
        content = (out / "server.js").read_text(encoding="utf-8")
        assert "BEARER_TOKEN" not in content

    def test_server_name_in_package_json(self, tmp_path: Path) -> None:
        out = tmp_path / "server"
        generate(
            tool_definitions=[_minimal_tool()],
            spec=_minimal_spec(),
            language="node",
            output_dir=out,
            server_name="Pet Store",
        )
        content = (out / "package.json").read_text(encoding="utf-8")
        # Template lowercases and hyphenates the server name.
        assert "pet-store" in content


# ---------------------------------------------------------------------------
# generate() – error cases
# ---------------------------------------------------------------------------


class TestGenerateErrors:
    """Error handling tests for generate()."""

    def test_unsupported_language_raises(self, tmp_path: Path) -> None:
        with pytest.raises(GeneratorError, match="Unsupported language"):
            generate(
                tool_definitions=[],
                spec=_minimal_spec(),
                language="rust",
                output_dir=tmp_path / "out",
            )

    def test_unwritable_output_dir_raises(self, tmp_path: Path) -> None:
        """Writing to a path where a file already exists as the dir name should fail."""
        # Create a file where the output dir should be.
        blocker = tmp_path / "blocker"
        blocker.write_text("I am a file", encoding="utf-8")
        # Now try to use it as a directory.
        with pytest.raises((GeneratorError, OSError)):
            generate(
                tool_definitions=[],
                spec=_minimal_spec(),
                language="python",
                output_dir=blocker / "subdir",
            )


# ---------------------------------------------------------------------------
# Petstore integration test
# ---------------------------------------------------------------------------


class TestGeneratePetstore:
    """Full pipeline integration: petstore fixture → generator → file assertions."""

    def setup_method(self) -> None:
        self.spec = _load_petstore()
        self.tools = parse_spec(self.spec)

    def test_generates_python_server_from_petstore(self, tmp_path: Path) -> None:
        out = tmp_path / "petstore_server"
        written = generate(
            tool_definitions=self.tools,
            spec=self.spec,
            language="python",
            output_dir=out,
        )
        assert len(written) == 3
        assert (out / "server.py").is_file()
        assert (out / "tools.py").is_file()
        assert (out / "requirements.txt").is_file()

    def test_python_tools_contains_all_operations(self, tmp_path: Path) -> None:
        out = tmp_path / "petstore_py"
        generate(
            tool_definitions=self.tools,
            spec=self.spec,
            language="python",
            output_dir=out,
        )
        content = (out / "tools.py").read_text(encoding="utf-8")
        for tool in self.tools:
            assert tool.name in content, f"Missing tool: {tool.name}"

    def test_python_server_contains_all_tool_names(self, tmp_path: Path) -> None:
        out = tmp_path / "petstore_py"
        generate(
            tool_definitions=self.tools,
            spec=self.spec,
            language="python",
            output_dir=out,
        )
        content = (out / "server.py").read_text(encoding="utf-8")
        for tool in self.tools:
            assert tool.name in content, f"Missing tool: {tool.name}"

    def test_python_server_contains_base_url(self, tmp_path: Path) -> None:
        out = tmp_path / "petstore_py"
        generate(
            tool_definitions=self.tools,
            spec=self.spec,
            language="python",
            output_dir=out,
        )
        content = (out / "server.py").read_text(encoding="utf-8")
        assert "petstore.example.com" in content

    def test_python_server_contains_bearer_token(self, tmp_path: Path) -> None:
        out = tmp_path / "petstore_py"
        generate(
            tool_definitions=self.tools,
            spec=self.spec,
            language="python",
            output_dir=out,
            include_auth=True,
        )
        content = (out / "server.py").read_text(encoding="utf-8")
        assert "BEARER_TOKEN" in content

    def test_generates_node_server_from_petstore(self, tmp_path: Path) -> None:
        out = tmp_path / "petstore_node"
        written = generate(
            tool_definitions=self.tools,
            spec=self.spec,
            language="node",
            output_dir=out,
        )
        assert len(written) == 3
        assert (out / "server.js").is_file()
        assert (out / "tools.js").is_file()
        assert (out / "package.json").is_file()

    def test_node_tools_contains_all_operations(self, tmp_path: Path) -> None:
        out = tmp_path / "petstore_node"
        generate(
            tool_definitions=self.tools,
            spec=self.spec,
            language="node",
            output_dir=out,
        )
        content = (out / "tools.js").read_text(encoding="utf-8")
        for tool in self.tools:
            assert tool.name in content, f"Missing tool: {tool.name}"

    def test_node_package_json_is_valid_structure(self, tmp_path: Path) -> None:
        import json as _json

        out = tmp_path / "petstore_node"
        generate(
            tool_definitions=self.tools,
            spec=self.spec,
            language="node",
            output_dir=out,
        )
        raw = (out / "package.json").read_text(encoding="utf-8")
        pkg = _json.loads(raw)
        assert "name" in pkg
        assert "dependencies" in pkg
        assert "@modelcontextprotocol/sdk" in pkg["dependencies"]

    def test_tools_py_contains_input_schema(self, tmp_path: Path) -> None:
        out = tmp_path / "petstore_py"
        generate(
            tool_definitions=self.tools,
            spec=self.spec,
            language="python",
            output_dir=out,
        )
        content = (out / "tools.py").read_text(encoding="utf-8")
        assert "inputSchema" in content

    def test_tools_py_contains_path_parameter_substitution(self, tmp_path: Path) -> None:
        out = tmp_path / "petstore_py"
        generate(
            tool_definitions=self.tools,
            spec=self.spec,
            language="python",
            output_dir=out,
        )
        content = (out / "tools.py").read_text(encoding="utf-8")
        # petId is a path parameter – its substitution code should appear
        assert "petId" in content


# ---------------------------------------------------------------------------
# _get_template_plan
# ---------------------------------------------------------------------------


class TestGetTemplatePlan:
    """Tests for _get_template_plan."""

    def test_python_plan_has_three_entries(self) -> None:
        plan = _get_template_plan("python")
        assert len(plan) == 3

    def test_python_plan_filenames(self) -> None:
        plan = _get_template_plan("python")
        output_files = [f for _, f in plan]
        assert "server.py" in output_files
        assert "tools.py" in output_files
        assert "requirements.txt" in output_files

    def test_node_plan_has_three_entries(self) -> None:
        plan = _get_template_plan("node")
        assert len(plan) == 3

    def test_node_plan_filenames(self) -> None:
        plan = _get_template_plan("node")
        output_files = [f for _, f in plan]
        assert "server.js" in output_files
        assert "tools.js" in output_files
        assert "package.json" in output_files

    def test_unknown_language_raises(self) -> None:
        with pytest.raises(GeneratorError):
            _get_template_plan("go")


# ---------------------------------------------------------------------------
# _extract_base_url
# ---------------------------------------------------------------------------


class TestExtractBaseUrl:
    """Tests for _extract_base_url in generator module."""

    def test_extracts_from_servers(self) -> None:
        spec = _minimal_spec(servers=[{"url": "https://api.example.com/v2"}])
        assert _extract_base_url(spec) == "https://api.example.com/v2"

    def test_returns_empty_when_no_servers(self) -> None:
        spec = _minimal_spec()
        assert _extract_base_url(spec) == ""

    def test_returns_first_server_url(self) -> None:
        spec = _minimal_spec(
            servers=[
                {"url": "https://prod.example.com"},
                {"url": "https://staging.example.com"},
            ]
        )
        assert _extract_base_url(spec) == "https://prod.example.com"


# ---------------------------------------------------------------------------
# _collect_security_schemes
# ---------------------------------------------------------------------------


class TestCollectSecuritySchemes:
    """Tests for _collect_security_schemes."""

    def test_empty_tools_returns_empty(self) -> None:
        result = _collect_security_schemes([])
        assert result == []

    def test_collects_schemes_from_single_tool(self) -> None:
        tool = _minimal_tool()
        tool.security_schemes.append(_bearer_scheme())
        result = _collect_security_schemes([tool])
        assert len(result) == 1
        assert result[0].name == "bearerAuth"

    def test_deduplicates_schemes(self) -> None:
        tool1 = _minimal_tool(name="t1")
        tool1.security_schemes.append(_bearer_scheme())
        tool2 = _minimal_tool(name="t2")
        tool2.security_schemes.append(_bearer_scheme())
        result = _collect_security_schemes([tool1, tool2])
        assert len(result) == 1

    def test_collects_multiple_distinct_schemes(self) -> None:
        tool = _minimal_tool()
        tool.security_schemes.append(_bearer_scheme())
        tool.security_schemes.append(_api_key_scheme())
        result = _collect_security_schemes([tool])
        assert len(result) == 2
        names = {s.name for s in result}
        assert "bearerAuth" in names
        assert "apiKey" in names

    def test_preserves_order_of_first_occurrence(self) -> None:
        tool1 = _minimal_tool(name="t1")
        tool1.security_schemes.append(_bearer_scheme())
        tool2 = _minimal_tool(name="t2")
        tool2.security_schemes.append(_api_key_scheme())
        result = _collect_security_schemes([tool1, tool2])
        assert result[0].name == "bearerAuth"
        assert result[1].name == "apiKey"


# ---------------------------------------------------------------------------
# _write_file
# ---------------------------------------------------------------------------


class TestWriteFile:
    """Tests for _write_file."""

    def test_writes_content(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.txt"
        _write_file(dest, "hello world")
        assert dest.read_text(encoding="utf-8") == "hello world"

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        dest = tmp_path / "a" / "b" / "c" / "file.txt"
        _write_file(dest, "content")
        assert dest.is_file()

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        dest = tmp_path / "file.txt"
        dest.write_text("old content", encoding="utf-8")
        _write_file(dest, "new content")
        assert dest.read_text(encoding="utf-8") == "new content"


# ---------------------------------------------------------------------------
# _render_template
# ---------------------------------------------------------------------------


class TestRenderTemplate:
    """Tests for _render_template."""

    def test_renders_python_server_template(self) -> None:
        env = _build_jinja_env()
        context = {
            "tools": [_minimal_tool()],
            "server_name": "Test Server",
            "base_url": "https://api.example.com",
            "language": "python",
            "include_auth": False,
            "security_schemes": [],
            "spec": _minimal_spec(),
        }
        result = _render_template(env, "python/server.py.j2", context)
        assert isinstance(result, str)
        assert "Test Server" in result

    def test_renders_python_tools_template(self) -> None:
        env = _build_jinja_env()
        context = {
            "tools": [_minimal_tool(name="list_items")],
            "server_name": "Test Server",
            "base_url": "",
            "language": "python",
            "include_auth": False,
            "security_schemes": [],
            "spec": _minimal_spec(),
        }
        result = _render_template(env, "python/tools.py.j2", context)
        assert "list_items" in result
        assert "TOOL_DEFINITIONS" in result

    def test_renders_node_server_template(self) -> None:
        env = _build_jinja_env()
        context = {
            "tools": [_minimal_tool(name="get_thing")],
            "server_name": "Node Server",
            "base_url": "",
            "language": "node",
            "include_auth": False,
            "security_schemes": [],
            "spec": _minimal_spec(),
        }
        result = _render_template(env, "node/server.js.j2", context)
        assert "Node Server" in result
        assert "get_thing" in result

    def test_missing_template_raises_generator_error(self) -> None:
        env = _build_jinja_env()
        with pytest.raises(GeneratorError, match="Template not found"):
            _render_template(env, "nonexistent/template.j2", {})
