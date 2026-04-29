"""Unit tests for mcp_forge.parser.

Covers parsing of parameters, request bodies, security schemes, tool name
derivation, $ref resolution, and the full parse_spec pipeline against the
petstore fixture.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from mcp_forge.models import (
    ParameterLocation,
    SecuritySchemeType,
    ToolDefinition,
)
from mcp_forge.parser import (
    ParserError,
    _derive_tool_name,
    _extract_base_url,
    _extract_body_fields,
    _extract_response_schema,
    _extract_security_schemes_map,
    _merge_parameters,
    _parse_operation,
    _parse_parameter,
    _parse_request_body,
    _parse_security_scheme,
    _pick_content_type,
    _resolve_ref,
    _resolve_security_schemes,
    _slugify,
    parse_spec,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).parent / "fixtures"
PETSTORE_YAML = FIXTURE_DIR / "petstore.yaml"


def _load_petstore() -> dict[str, Any]:
    """Load and return the petstore YAML fixture as a dict."""
    return yaml.safe_load(PETSTORE_YAML.read_text(encoding="utf-8"))


def _minimal_spec(**extra: Any) -> dict[str, Any]:
    """Build a minimal valid spec dict for testing."""
    spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Test", "version": "1.0.0"},
        "paths": {},
    }
    spec.update(extra)
    return spec


# ---------------------------------------------------------------------------
# parse_spec – petstore fixture (integration)
# ---------------------------------------------------------------------------


class TestParseSpecPetstore:
    """Integration tests running parse_spec against the full petstore fixture."""

    def setup_method(self) -> None:
        self.spec = _load_petstore()
        self.tools = parse_spec(self.spec)

    def test_returns_list(self) -> None:
        assert isinstance(self.tools, list)

    def test_correct_number_of_tools(self) -> None:
        """Petstore has 5 operations: listPets, createPet, getPetById, updatePet, deletePet."""
        assert len(self.tools) == 5

    def test_all_items_are_tool_definitions(self) -> None:
        for tool in self.tools:
            assert isinstance(tool, ToolDefinition)

    def test_tool_names_unique(self) -> None:
        names = [t.name for t in self.tools]
        assert len(names) == len(set(names))

    def test_list_pets_tool_present(self) -> None:
        names = [t.name for t in self.tools]
        assert "listpets" in names

    def test_create_pet_tool_present(self) -> None:
        names = [t.name for t in self.tools]
        assert "createpet" in names

    def test_get_pet_by_id_tool_present(self) -> None:
        names = [t.name for t in self.tools]
        assert "getpetbyid" in names

    def test_update_pet_tool_present(self) -> None:
        names = [t.name for t in self.tools]
        assert "updatepet" in names

    def test_delete_pet_tool_present(self) -> None:
        names = [t.name for t in self.tools]
        assert "deletepet" in names

    def test_list_pets_method_is_get(self) -> None:
        tool = next(t for t in self.tools if t.name == "listpets")
        assert tool.http_method == "GET"

    def test_create_pet_method_is_post(self) -> None:
        tool = next(t for t in self.tools if t.name == "createpet")
        assert tool.http_method == "POST"

    def test_delete_pet_method_is_delete(self) -> None:
        tool = next(t for t in self.tools if t.name == "deletepet")
        assert tool.http_method == "DELETE"

    def test_list_pets_has_query_parameters(self) -> None:
        tool = next(t for t in self.tools if t.name == "listpets")
        param_names = [p.name for p in tool.query_parameters]
        assert "limit" in param_names
        assert "status" in param_names

    def test_get_pet_by_id_has_path_parameter(self) -> None:
        tool = next(t for t in self.tools if t.name == "getpetbyid")
        path_param_names = [p.name for p in tool.path_parameters]
        assert "petId" in path_param_names

    def test_path_parameter_is_required(self) -> None:
        tool = next(t for t in self.tools if t.name == "getpetbyid")
        pet_id_param = next(p for p in tool.parameters if p.name == "petId")
        assert pet_id_param.required is True

    def test_list_pets_limit_param_schema(self) -> None:
        tool = next(t for t in self.tools if t.name == "listpets")
        limit = next(p for p in tool.parameters if p.name == "limit")
        assert limit.schema["type"] == "integer"

    def test_create_pet_has_request_body(self) -> None:
        tool = next(t for t in self.tools if t.name == "createpet")
        assert tool.has_body is True
        assert tool.request_body is not None

    def test_create_pet_request_body_required(self) -> None:
        tool = next(t for t in self.tools if t.name == "createpet")
        assert tool.request_body.required is True  # type: ignore[union-attr]

    def test_create_pet_request_body_has_fields(self) -> None:
        tool = next(t for t in self.tools if t.name == "createpet")
        field_names = [f.name for f in tool.request_body.fields]  # type: ignore[union-attr]
        assert "name" in field_names

    def test_create_pet_name_field_required(self) -> None:
        tool = next(t for t in self.tools if t.name == "createpet")
        name_field = next(
            f for f in tool.request_body.fields if f.name == "name"  # type: ignore[union-attr]
        )
        assert name_field.required is True

    def test_list_pets_has_no_request_body(self) -> None:
        tool = next(t for t in self.tools if t.name == "listpets")
        assert tool.has_body is False

    def test_tools_have_security_schemes(self) -> None:
        """All operations inherit global bearerAuth security."""
        for tool in self.tools:
            assert tool.requires_auth is True

    def test_bearer_auth_scheme_present(self) -> None:
        tool = next(t for t in self.tools if t.name == "listpets")
        scheme_names = [s.name for s in tool.security_schemes]
        assert "bearerAuth" in scheme_names

    def test_bearer_auth_is_http_type(self) -> None:
        tool = next(t for t in self.tools if t.name == "listpets")
        bearer = next(s for s in tool.security_schemes if s.name == "bearerAuth")
        assert bearer.scheme_type == SecuritySchemeType.HTTP
        assert bearer.is_bearer is True

    def test_list_pets_has_tags(self) -> None:
        tool = next(t for t in self.tools if t.name == "listpets")
        assert "pets" in tool.tags

    def test_operation_id_preserved(self) -> None:
        tool = next(t for t in self.tools if t.name == "listpets")
        assert tool.operation_id == "listPets"

    def test_base_url_extracted(self) -> None:
        for tool in self.tools:
            assert tool.base_url == "https://petstore.example.com/v1"

    def test_list_pets_path(self) -> None:
        tool = next(t for t in self.tools if t.name == "listpets")
        assert tool.path == "/pets"

    def test_get_pet_by_id_path(self) -> None:
        tool = next(t for t in self.tools if t.name == "getpetbyid")
        assert tool.path == "/pets/{petId}"

    def test_list_pets_description_not_empty(self) -> None:
        tool = next(t for t in self.tools if t.name == "listpets")
        assert len(tool.description) > 0

    def test_list_pets_response_schema(self) -> None:
        """listPets 200 response has an array schema."""
        tool = next(t for t in self.tools if t.name == "listpets")
        # The schema is an array of Pet refs – after ref resolution it should
        # be a dict with 'type': 'array'.
        assert isinstance(tool.response_schema, dict)

    def test_input_schema_has_type_object(self) -> None:
        for tool in self.tools:
            schema = tool.input_schema
            assert schema["type"] == "object"


# ---------------------------------------------------------------------------
# parse_spec – edge cases
# ---------------------------------------------------------------------------


class TestParseSpecEdgeCases:
    """Edge cases and unusual input shapes for parse_spec."""

    def test_empty_paths_returns_empty_list(self) -> None:
        spec = _minimal_spec(paths={})
        assert parse_spec(spec) == []

    def test_missing_paths_returns_empty_list(self) -> None:
        spec = {
            "openapi": "3.0.3",
            "info": {"title": "T", "version": "1"},
            "components": {},
        }
        assert parse_spec(spec) == []

    def test_paths_none_returns_empty_list(self) -> None:
        spec = _minimal_spec()
        spec["paths"] = None
        assert parse_spec(spec) == []

    def test_paths_not_dict_raises(self) -> None:
        spec = _minimal_spec()
        spec["paths"] = ["not", "a", "dict"]
        with pytest.raises(ParserError):
            parse_spec(spec)

    def test_non_dict_path_item_skipped(self) -> None:
        spec = _minimal_spec(paths={"/pets": "not_a_dict"})
        result = parse_spec(spec)
        assert result == []

    def test_operation_without_operation_id(self) -> None:
        spec = _minimal_spec(
            paths={
                "/items": {
                    "get": {
                        "summary": "List items",
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            }
        )
        tools = parse_spec(spec)
        assert len(tools) == 1
        assert tools[0].name  # non-empty
        assert tools[0].http_method == "GET"

    def test_operation_id_used_as_name(self) -> None:
        spec = _minimal_spec(
            paths={
                "/items": {
                    "get": {
                        "operationId": "listItems",
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            }
        )
        tools = parse_spec(spec)
        assert tools[0].name == "listitems"

    def test_duplicate_operation_ids_get_unique_names(self) -> None:
        spec = _minimal_spec(
            paths={
                "/a": {
                    "get": {
                        "operationId": "myOp",
                        "responses": {"200": {"description": "OK"}},
                    }
                },
                "/b": {
                    "get": {
                        "operationId": "myOp",
                        "responses": {"200": {"description": "OK"}},
                    }
                },
            }
        )
        tools = parse_spec(spec)
        assert len(tools) == 2
        names = [t.name for t in tools]
        assert len(set(names)) == 2

    def test_no_security_schemes_gives_empty_auth(self) -> None:
        spec = _minimal_spec(
            paths={
                "/items": {
                    "get": {
                        "operationId": "listItems",
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            }
        )
        tools = parse_spec(spec)
        assert tools[0].requires_auth is False

    def test_operation_level_security_overrides_global(self) -> None:
        """An operation with security: [] should have no auth even with global security."""
        spec = _minimal_spec(
            security=[{"bearerAuth": []}],
            paths={
                "/public": {
                    "get": {
                        "operationId": "publicEndpoint",
                        "security": [],
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
            components={
                "securitySchemes": {
                    "bearerAuth": {"type": "http", "scheme": "bearer"}
                }
            },
        )
        tools = parse_spec(spec)
        assert tools[0].requires_auth is False

    def test_deprecated_flag_propagated(self) -> None:
        spec = _minimal_spec(
            paths={
                "/old": {
                    "get": {
                        "operationId": "oldOp",
                        "deprecated": True,
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            }
        )
        tools = parse_spec(spec)
        assert tools[0].deprecated is True

    def test_non_deprecated_default_false(self) -> None:
        spec = _minimal_spec(
            paths={
                "/new": {
                    "get": {
                        "operationId": "newOp",
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            }
        )
        tools = parse_spec(spec)
        assert tools[0].deprecated is False

    def test_path_level_parameters_inherited(self) -> None:
        spec = _minimal_spec(
            paths={
                "/items/{itemId}": {
                    "parameters": [
                        {
                            "name": "itemId",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "get": {
                        "operationId": "getItem",
                        "responses": {"200": {"description": "OK"}},
                    },
                    "delete": {
                        "operationId": "deleteItem",
                        "responses": {"204": {"description": "No Content"}},
                    },
                }
            }
        )
        tools = parse_spec(spec)
        for tool in tools:
            param_names = [p.name for p in tool.path_parameters]
            assert "itemId" in param_names

    def test_operation_param_overrides_path_param(self) -> None:
        spec = _minimal_spec(
            paths={
                "/items/{itemId}": {
                    "parameters": [
                        {
                            "name": "itemId",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                            "description": "from path",
                        }
                    ],
                    "get": {
                        "operationId": "getItem",
                        "parameters": [
                            {
                                "name": "itemId",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "integer"},
                                "description": "from operation",
                            }
                        ],
                        "responses": {"200": {"description": "OK"}},
                    },
                }
            }
        )
        tools = parse_spec(spec)
        item_id_param = next(p for p in tools[0].parameters if p.name == "itemId")
        assert item_id_param.schema["type"] == "integer"
        assert item_id_param.description == "from operation"


# ---------------------------------------------------------------------------
# _slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    """Tests for the _slugify helper."""

    def test_simple_camel_case(self) -> None:
        assert _slugify("listPets") == "listpets"

    def test_path_separators_become_underscores(self) -> None:
        result = _slugify("/pets/{petId}")
        assert "/" not in result
        assert "{" not in result
        assert "}" not in result

    def test_consecutive_underscores_collapsed(self) -> None:
        result = _slugify("/pets/{petId}")
        assert "__" not in result

    def test_hyphen_becomes_underscore(self) -> None:
        assert "-" not in _slugify("get-pet-by-id")

    def test_lowercase_output(self) -> None:
        result = _slugify("GetPetByID")
        assert result == result.lower()

    def test_leading_digit_prefixed(self) -> None:
        result = _slugify("123abc")
        assert not result[0].isdigit()

    def test_empty_string_returns_operation(self) -> None:
        assert _slugify("") == "operation"

    def test_no_leading_trailing_underscores(self) -> None:
        result = _slugify("/pets/")
        assert not result.startswith("_")
        assert not result.endswith("_")


# ---------------------------------------------------------------------------
# _derive_tool_name
# ---------------------------------------------------------------------------


class TestDeriveToolName:
    """Tests for the _derive_tool_name helper."""

    def test_uses_operation_id_when_present(self) -> None:
        name = _derive_tool_name("get", "/pets", "listPets", set())
        assert name == "listpets"

    def test_falls_back_to_method_path(self) -> None:
        name = _derive_tool_name("get", "/pets", None, set())
        assert "get" in name
        assert "pets" in name

    def test_deduplicates_with_suffix(self) -> None:
        seen: set[str] = {"listpets"}
        name = _derive_tool_name("get", "/pets", "listPets", seen)
        assert name != "listpets"
        assert name.startswith("listpets")

    def test_adds_to_seen_names_externally(self) -> None:
        """The caller is responsible for adding returned name to seen_names."""
        seen: set[str] = set()
        name = _derive_tool_name("get", "/pets", "listPets", seen)
        assert name not in seen  # caller must add it


# ---------------------------------------------------------------------------
# _parse_parameter
# ---------------------------------------------------------------------------


class TestParseParameter:
    """Tests for the _parse_parameter helper."""

    def test_basic_query_parameter(self) -> None:
        raw = {"name": "limit", "in": "query", "schema": {"type": "integer"}}
        param = _parse_parameter(raw)
        assert param.name == "limit"
        assert param.location == ParameterLocation.QUERY
        assert param.schema["type"] == "integer"

    def test_path_parameter_is_always_required(self) -> None:
        raw = {
            "name": "petId",
            "in": "path",
            "required": False,
            "schema": {"type": "integer"},
        }
        param = _parse_parameter(raw)
        assert param.required is True

    def test_query_param_not_required_by_default(self) -> None:
        raw = {"name": "q", "in": "query", "schema": {"type": "string"}}
        param = _parse_parameter(raw)
        assert param.required is False

    def test_required_query_param(self) -> None:
        raw = {
            "name": "q",
            "in": "query",
            "required": True,
            "schema": {"type": "string"},
        }
        param = _parse_parameter(raw)
        assert param.required is True

    def test_description_extracted(self) -> None:
        raw = {
            "name": "q",
            "in": "query",
            "description": "search term",
            "schema": {"type": "string"},
        }
        param = _parse_parameter(raw)
        assert param.description == "search term"

    def test_example_extracted_from_param(self) -> None:
        raw = {
            "name": "status",
            "in": "query",
            "schema": {"type": "string"},
            "example": "available",
        }
        param = _parse_parameter(raw)
        assert param.example == "available"

    def test_example_falls_back_to_schema_example(self) -> None:
        raw = {
            "name": "status",
            "in": "query",
            "schema": {"type": "string", "example": "pending"},
        }
        param = _parse_parameter(raw)
        assert param.example == "pending"

    def test_unknown_in_falls_back_to_query(self) -> None:
        raw = {"name": "x", "in": "unknown_location", "schema": {"type": "string"}}
        param = _parse_parameter(raw)
        assert param.location == ParameterLocation.QUERY

    def test_header_location(self) -> None:
        raw = {"name": "X-Trace-Id", "in": "header", "schema": {"type": "string"}}
        param = _parse_parameter(raw)
        assert param.location == ParameterLocation.HEADER

    def test_missing_schema_defaults_to_string(self) -> None:
        raw = {"name": "q", "in": "query"}
        param = _parse_parameter(raw)
        assert param.schema == {"type": "string"}


# ---------------------------------------------------------------------------
# _parse_request_body
# ---------------------------------------------------------------------------


class TestParseRequestBody:
    """Tests for the _parse_request_body helper."""

    def _spec_with_schema(self, schema: dict) -> dict[str, Any]:
        """Build a spec containing the given schema as a component."""
        return {
            "openapi": "3.0.3",
            "info": {"title": "T", "version": "1"},
            "components": {"schemas": {"Body": schema}},
            "paths": {},
        }

    def test_basic_json_body(self) -> None:
        rb_raw = {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {"type": "object", "properties": {}}
                }
            },
        }
        rb = _parse_request_body(rb_raw, {})
        assert rb.required is True
        assert rb.content_type == "application/json"

    def test_extracts_object_properties_as_fields(self) -> None:
        rb_raw = {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["name"],
                        "properties": {
                            "name": {"type": "string"},
                            "age": {"type": "integer"},
                        },
                    }
                }
            },
        }
        rb = _parse_request_body(rb_raw, {})
        field_names = [f.name for f in rb.fields]
        assert "name" in field_names
        assert "age" in field_names

    def test_required_fields_marked_correctly(self) -> None:
        rb_raw = {
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["email"],
                        "properties": {
                            "email": {"type": "string"},
                            "phone": {"type": "string"},
                        },
                    }
                }
            }
        }
        rb = _parse_request_body(rb_raw, {})
        email_field = next(f for f in rb.fields if f.name == "email")
        phone_field = next(f for f in rb.fields if f.name == "phone")
        assert email_field.required is True
        assert phone_field.required is False

    def test_no_content_gives_empty_body(self) -> None:
        rb_raw = {"required": False}
        rb = _parse_request_body(rb_raw, {})
        assert rb.fields == []
        assert rb.schema == {}

    def test_prefers_json_over_form(self) -> None:
        rb_raw = {
            "content": {
                "application/x-www-form-urlencoded": {
                    "schema": {"type": "object", "properties": {}}
                },
                "application/json": {
                    "schema": {"type": "object", "properties": {}}
                },
            }
        }
        rb = _parse_request_body(rb_raw, {})
        assert rb.content_type == "application/json"

    def test_description_extracted(self) -> None:
        rb_raw = {
            "description": "The pet to create",
            "content": {
                "application/json": {
                    "schema": {"type": "object", "properties": {}}
                }
            },
        }
        rb = _parse_request_body(rb_raw, {})
        assert rb.description == "The pet to create"

    def test_ref_in_schema_resolved(self) -> None:
        spec: dict[str, Any] = {
            "openapi": "3.0.3",
            "info": {"title": "T", "version": "1"},
            "components": {
                "schemas": {
                    "NewPet": {
                        "type": "object",
                        "required": ["name"],
                        "properties": {"name": {"type": "string"}},
                    }
                }
            },
            "paths": {},
        }
        rb_raw = {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/NewPet"}
                }
            },
        }
        rb = _parse_request_body(rb_raw, spec)
        field_names = [f.name for f in rb.fields]
        assert "name" in field_names


# ---------------------------------------------------------------------------
# _pick_content_type
# ---------------------------------------------------------------------------


class TestPickContentType:
    """Tests for the _pick_content_type helper."""

    def test_prefers_json(self) -> None:
        content = {
            "application/json": {},
            "application/x-www-form-urlencoded": {},
        }
        assert _pick_content_type(content) == "application/json"

    def test_falls_back_to_form_urlencoded(self) -> None:
        content = {"application/x-www-form-urlencoded": {}}
        assert _pick_content_type(content) == "application/x-www-form-urlencoded"

    def test_falls_back_to_multipart(self) -> None:
        content = {"multipart/form-data": {}}
        assert _pick_content_type(content) == "multipart/form-data"

    def test_first_available_when_no_preferred(self) -> None:
        content = {"text/plain": {}}
        result = _pick_content_type(content)
        assert result == "text/plain"

    def test_empty_content_returns_none(self) -> None:
        assert _pick_content_type({}) is None


# ---------------------------------------------------------------------------
# _extract_body_fields
# ---------------------------------------------------------------------------


class TestExtractBodyFields:
    """Tests for the _extract_body_fields helper."""

    def test_object_schema_with_properties(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "count": {"type": "integer"},
            },
        }
        fields = _extract_body_fields(schema, {})
        names = [f.name for f in fields]
        assert "name" in names
        assert "count" in names

    def test_array_schema_returns_empty(self) -> None:
        schema = {"type": "array", "items": {"type": "string"}}
        fields = _extract_body_fields(schema, {})
        assert fields == []

    def test_primitive_schema_returns_empty(self) -> None:
        schema = {"type": "string"}
        fields = _extract_body_fields(schema, {})
        assert fields == []

    def test_required_array_marks_fields(self) -> None:
        schema = {
            "type": "object",
            "required": ["email"],
            "properties": {
                "email": {"type": "string"},
                "nickname": {"type": "string"},
            },
        }
        fields = _extract_body_fields(schema, {})
        email = next(f for f in fields if f.name == "email")
        nick = next(f for f in fields if f.name == "nickname")
        assert email.required is True
        assert nick.required is False

    def test_no_properties_key_returns_empty(self) -> None:
        schema = {"type": "object"}
        fields = _extract_body_fields(schema, {})
        assert fields == []

    def test_description_from_property_schema(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Full name"},
            },
        }
        fields = _extract_body_fields(schema, {})
        assert fields[0].description == "Full name"


# ---------------------------------------------------------------------------
# _parse_security_scheme
# ---------------------------------------------------------------------------


class TestParseSecurityScheme:
    """Tests for the _parse_security_scheme helper."""

    def test_bearer_http_scheme(self) -> None:
        raw = {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
        scheme = _parse_security_scheme("bearerAuth", raw)
        assert scheme.name == "bearerAuth"
        assert scheme.scheme_type == SecuritySchemeType.HTTP
        assert scheme.is_bearer is True
        assert scheme.bearer_format == "JWT"

    def test_api_key_scheme(self) -> None:
        raw = {"type": "apiKey", "in": "header", "name": "X-API-Key"}
        scheme = _parse_security_scheme("apiKey", raw)
        assert scheme.scheme_type == SecuritySchemeType.API_KEY
        assert scheme.api_key_in == "header"
        assert scheme.api_key_name == "X-API-Key"
        assert scheme.is_api_key is True

    def test_oauth2_scheme(self) -> None:
        raw = {"type": "oauth2", "flows": {}}
        scheme = _parse_security_scheme("oauth", raw)
        assert scheme.scheme_type == SecuritySchemeType.OAUTH2

    def test_unknown_type_becomes_other(self) -> None:
        raw = {"type": "custom"}
        scheme = _parse_security_scheme("custom", raw)
        assert scheme.scheme_type == SecuritySchemeType.OTHER

    def test_description_extracted(self) -> None:
        raw = {"type": "http", "scheme": "bearer", "description": "JWT auth"}
        scheme = _parse_security_scheme("s", raw)
        assert scheme.description == "JWT auth"


# ---------------------------------------------------------------------------
# _extract_security_schemes_map
# ---------------------------------------------------------------------------


class TestExtractSecuritySchemesMap:
    """Tests for _extract_security_schemes_map."""

    def test_returns_empty_when_no_components(self) -> None:
        spec = _minimal_spec()
        result = _extract_security_schemes_map(spec)
        assert result == {}

    def test_returns_empty_when_no_security_schemes(self) -> None:
        spec = _minimal_spec(components={})
        result = _extract_security_schemes_map(spec)
        assert result == {}

    def test_extracts_bearer_scheme(self) -> None:
        spec = _minimal_spec(
            components={
                "securitySchemes": {
                    "bearerAuth": {"type": "http", "scheme": "bearer"}
                }
            }
        )
        result = _extract_security_schemes_map(spec)
        assert "bearerAuth" in result
        assert result["bearerAuth"].is_bearer is True

    def test_extracts_multiple_schemes(self) -> None:
        spec = _minimal_spec(
            components={
                "securitySchemes": {
                    "bearerAuth": {"type": "http", "scheme": "bearer"},
                    "apiKey": {"type": "apiKey", "in": "header", "name": "X-Key"},
                }
            }
        )
        result = _extract_security_schemes_map(spec)
        assert "bearerAuth" in result
        assert "apiKey" in result


# ---------------------------------------------------------------------------
# _resolve_security_schemes
# ---------------------------------------------------------------------------


class TestResolveSecuritySchemes:
    """Tests for _resolve_security_schemes."""

    def _bearer_scheme_map(self) -> dict:
        from mcp_forge.models import SecurityScheme
        return {
            "bearerAuth": SecurityScheme(
                name="bearerAuth",
                scheme_type=SecuritySchemeType.HTTP,
                http_scheme="bearer",
            )
        }

    def test_resolves_known_scheme(self) -> None:
        schemes_map = self._bearer_scheme_map()
        reqs = [{"bearerAuth": []}]
        result = _resolve_security_schemes(reqs, schemes_map)
        assert len(result) == 1
        assert result[0].name == "bearerAuth"

    def test_unknown_scheme_silently_skipped(self) -> None:
        schemes_map = self._bearer_scheme_map()
        reqs = [{"unknownScheme": []}]
        result = _resolve_security_schemes(reqs, schemes_map)
        assert result == []

    def test_empty_security_list_returns_empty(self) -> None:
        schemes_map = self._bearer_scheme_map()
        result = _resolve_security_schemes([], schemes_map)
        assert result == []

    def test_deduplicates_schemes(self) -> None:
        schemes_map = self._bearer_scheme_map()
        reqs = [{"bearerAuth": []}, {"bearerAuth": ["read"]}]
        result = _resolve_security_schemes(reqs, schemes_map)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _resolve_ref
# ---------------------------------------------------------------------------


class TestResolveRef:
    """Tests for the _resolve_ref helper."""

    def _spec(self) -> dict[str, Any]:
        return {
            "openapi": "3.0.3",
            "info": {"title": "T", "version": "1"},
            "components": {
                "schemas": {
                    "Pet": {
                        "type": "object",
                        "properties": {"id": {"type": "integer"}},
                    }
                },
                "parameters": {
                    "PetId": {
                        "name": "petId",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "integer"},
                    }
                },
            },
            "paths": {},
        }

    def test_non_ref_object_returned_as_is(self) -> None:
        obj = {"type": "string"}
        result = _resolve_ref(obj, {})
        assert result is obj

    def test_non_dict_returned_as_is(self) -> None:
        assert _resolve_ref("string", {}) == "string"
        assert _resolve_ref(42, {}) == 42
        assert _resolve_ref(None, {}) is None

    def test_resolves_local_schema_ref(self) -> None:
        spec = self._spec()
        ref_obj = {"$ref": "#/components/schemas/Pet"}
        resolved = _resolve_ref(ref_obj, spec)
        assert isinstance(resolved, dict)
        assert resolved["type"] == "object"

    def test_resolves_local_parameter_ref(self) -> None:
        spec = self._spec()
        ref_obj = {"$ref": "#/components/parameters/PetId"}
        resolved = _resolve_ref(ref_obj, spec)
        assert resolved["name"] == "petId"

    def test_external_ref_returned_unchanged(self) -> None:
        ref_obj = {"$ref": "https://example.com/schemas/pet.json"}
        result = _resolve_ref(ref_obj, {})
        assert result is ref_obj

    def test_missing_ref_target_returned_as_is(self) -> None:
        ref_obj = {"$ref": "#/components/schemas/NonExistent"}
        spec = self._spec()
        result = _resolve_ref(ref_obj, spec)
        # Should return the original ref object unchanged.
        assert result is ref_obj or result == ref_obj

    def test_json_pointer_escaping(self) -> None:
        spec: dict[str, Any] = {
            "openapi": "3.0.3",
            "info": {"title": "T", "version": "1"},
            "components": {
                "schemas": {
                    "some~schema": {"type": "string"}
                }
            },
            "paths": {},
        }
        ref_obj = {"$ref": "#/components/schemas/some~0schema"}
        resolved = _resolve_ref(ref_obj, spec)
        assert resolved == {"type": "string"}


# ---------------------------------------------------------------------------
# _extract_base_url
# ---------------------------------------------------------------------------


class TestExtractBaseUrl:
    """Tests for the _extract_base_url helper."""

    def test_extracts_first_server_url(self) -> None:
        spec = _minimal_spec(servers=[{"url": "https://api.example.com/v1"}])
        assert _extract_base_url(spec) == "https://api.example.com/v1"

    def test_returns_empty_when_no_servers(self) -> None:
        spec = _minimal_spec()
        assert _extract_base_url(spec) == ""

    def test_returns_empty_when_servers_empty_list(self) -> None:
        spec = _minimal_spec(servers=[])
        assert _extract_base_url(spec) == ""

    def test_uses_first_server_only(self) -> None:
        spec = _minimal_spec(
            servers=[
                {"url": "https://prod.example.com"},
                {"url": "https://staging.example.com"},
            ]
        )
        assert _extract_base_url(spec) == "https://prod.example.com"


# ---------------------------------------------------------------------------
# _extract_response_schema
# ---------------------------------------------------------------------------


class TestExtractResponseSchema:
    """Tests for the _extract_response_schema helper."""

    def test_returns_empty_dict_when_no_responses(self) -> None:
        result = _extract_response_schema({}, {})
        assert result == {}

    def test_extracts_200_json_schema(self) -> None:
        responses = {
            "200": {
                "description": "OK",
                "content": {
                    "application/json": {
                        "schema": {"type": "object", "properties": {}}
                    }
                },
            }
        }
        result = _extract_response_schema(responses, {})
        assert result["type"] == "object"

    def test_prefers_200_over_201(self) -> None:
        responses = {
            "200": {
                "content": {
                    "application/json": {"schema": {"type": "string"}}
                }
            },
            "201": {
                "content": {
                    "application/json": {"schema": {"type": "integer"}}
                }
            },
        }
        result = _extract_response_schema(responses, {})
        assert result["type"] == "string"

    def test_returns_empty_for_non_2xx(self) -> None:
        responses = {
            "400": {
                "content": {
                    "application/json": {"schema": {"type": "object"}}
                }
            }
        }
        result = _extract_response_schema(responses, {})
        assert result == {}

    def test_resolves_ref_in_response_schema(self) -> None:
        spec: dict[str, Any] = {
            "openapi": "3.0.3",
            "info": {"title": "T", "version": "1"},
            "components": {
                "schemas": {"Pet": {"type": "object", "properties": {}}}
            },
            "paths": {},
        }
        responses = {
            "200": {
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/Pet"}
                    }
                }
            }
        }
        result = _extract_response_schema(responses, spec)
        assert result["type"] == "object"


# ---------------------------------------------------------------------------
# _merge_parameters
# ---------------------------------------------------------------------------


class TestMergeParameters:
    """Tests for the _merge_parameters helper."""

    def test_operation_overrides_path_param(self) -> None:
        path_params = [
            {"name": "petId", "in": "path", "schema": {"type": "string"}}
        ]
        op_params = [
            {"name": "petId", "in": "path", "schema": {"type": "integer"}}
        ]
        merged = _merge_parameters(path_params, op_params, {})
        assert len(merged) == 1
        assert merged[0]["schema"]["type"] == "integer"

    def test_different_name_params_both_kept(self) -> None:
        path_params = [{"name": "orgId", "in": "path", "schema": {"type": "string"}}]
        op_params = [{"name": "petId", "in": "path", "schema": {"type": "integer"}}]
        merged = _merge_parameters(path_params, op_params, {})
        names = [p["name"] for p in merged]
        assert "orgId" in names
        assert "petId" in names

    def test_empty_inputs(self) -> None:
        assert _merge_parameters([], [], {}) == []

    def test_only_path_params(self) -> None:
        path_params = [{"name": "id", "in": "path", "schema": {"type": "string"}}]
        merged = _merge_parameters(path_params, [], {})
        assert len(merged) == 1
        assert merged[0]["name"] == "id"
