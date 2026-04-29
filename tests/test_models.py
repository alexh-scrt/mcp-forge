"""Unit tests for mcp_forge.models.

Covers construction, default values, convenience properties, and the
``input_schema`` / ``to_json_schema_property`` helpers.
"""

from __future__ import annotations

from mcp_forge.models import (
    ParameterLocation,
    RequestBody,
    RequestBodyField,
    SecurityScheme,
    SecuritySchemeType,
    ToolDefinition,
    ToolParameter,
)


# ---------------------------------------------------------------------------
# ToolParameter
# ---------------------------------------------------------------------------


class TestToolParameter:
    """Tests for the ToolParameter dataclass."""

    def test_defaults(self) -> None:
        """Fields not supplied should have sensible defaults."""
        param = ToolParameter(name="pet_id", location=ParameterLocation.PATH)
        assert param.description == ""
        assert param.required is False
        assert param.schema == {"type": "string"}
        assert param.example is None

    def test_to_json_schema_property_basic(self) -> None:
        """Schema is echoed into the returned property dict."""
        param = ToolParameter(
            name="limit",
            location=ParameterLocation.QUERY,
            schema={"type": "integer"},
        )
        prop = param.to_json_schema_property()
        assert prop["type"] == "integer"

    def test_to_json_schema_property_includes_description(self) -> None:
        """A non-empty description must appear in the returned property."""
        param = ToolParameter(
            name="q",
            location=ParameterLocation.QUERY,
            description="Search query",
            schema={"type": "string"},
        )
        prop = param.to_json_schema_property()
        assert prop["description"] == "Search query"

    def test_to_json_schema_property_omits_empty_description(self) -> None:
        """An empty description must NOT appear in the returned property."""
        param = ToolParameter(
            name="q",
            location=ParameterLocation.QUERY,
            description="",
            schema={"type": "string"},
        )
        prop = param.to_json_schema_property()
        assert "description" not in prop

    def test_to_json_schema_property_includes_example(self) -> None:
        """An example value must be wrapped in a list under 'examples'."""
        param = ToolParameter(
            name="status",
            location=ParameterLocation.QUERY,
            schema={"type": "string"},
            example="available",
        )
        prop = param.to_json_schema_property()
        assert prop["examples"] == ["available"]

    def test_to_json_schema_property_no_example_key_when_none(self) -> None:
        """When example is None, 'examples' must not appear in the property."""
        param = ToolParameter(
            name="id",
            location=ParameterLocation.PATH,
            schema={"type": "integer"},
        )
        prop = param.to_json_schema_property()
        assert "examples" not in prop

    def test_original_schema_not_mutated(self) -> None:
        """to_json_schema_property must not mutate the original schema dict."""
        original_schema: dict = {"type": "string"}
        param = ToolParameter(
            name="x",
            location=ParameterLocation.HEADER,
            schema=original_schema,
            description="A header",
        )
        param.to_json_schema_property()
        assert "description" not in original_schema


# ---------------------------------------------------------------------------
# RequestBodyField
# ---------------------------------------------------------------------------


class TestRequestBodyField:
    """Tests for the RequestBodyField dataclass."""

    def test_defaults(self) -> None:
        field = RequestBodyField(name="email")
        assert field.description == ""
        assert field.required is False
        assert field.schema == {"type": "string"}

    def test_to_json_schema_property_with_description(self) -> None:
        field = RequestBodyField(
            name="name",
            description="Full name",
            schema={"type": "string"},
        )
        prop = field.to_json_schema_property()
        assert prop["description"] == "Full name"
        assert prop["type"] == "string"

    def test_to_json_schema_property_without_description(self) -> None:
        field = RequestBodyField(name="age", schema={"type": "integer"})
        prop = field.to_json_schema_property()
        assert "description" not in prop
        assert prop["type"] == "integer"

    def test_original_schema_not_mutated(self) -> None:
        original_schema: dict = {"type": "object"}
        field = RequestBodyField(
            name="data", description="payload", schema=original_schema
        )
        field.to_json_schema_property()
        assert "description" not in original_schema


# ---------------------------------------------------------------------------
# SecurityScheme
# ---------------------------------------------------------------------------


class TestSecurityScheme:
    """Tests for the SecurityScheme dataclass and its convenience properties."""

    def test_is_bearer_true(self) -> None:
        scheme = SecurityScheme(
            name="bearerAuth",
            scheme_type=SecuritySchemeType.HTTP,
            http_scheme="bearer",
        )
        assert scheme.is_bearer is True

    def test_is_bearer_case_insensitive(self) -> None:
        scheme = SecurityScheme(
            name="bearerAuth",
            scheme_type=SecuritySchemeType.HTTP,
            http_scheme="Bearer",
        )
        assert scheme.is_bearer is True

    def test_is_bearer_false_for_basic(self) -> None:
        scheme = SecurityScheme(
            name="basicAuth",
            scheme_type=SecuritySchemeType.HTTP,
            http_scheme="basic",
        )
        assert scheme.is_bearer is False

    def test_is_bearer_false_for_api_key(self) -> None:
        scheme = SecurityScheme(
            name="apiKey",
            scheme_type=SecuritySchemeType.API_KEY,
            api_key_in="header",
            api_key_name="X-API-Key",
        )
        assert scheme.is_bearer is False

    def test_is_api_key_true(self) -> None:
        scheme = SecurityScheme(
            name="apiKey",
            scheme_type=SecuritySchemeType.API_KEY,
            api_key_in="header",
            api_key_name="X-API-Key",
        )
        assert scheme.is_api_key is True

    def test_is_api_key_false_for_bearer(self) -> None:
        scheme = SecurityScheme(
            name="bearerAuth",
            scheme_type=SecuritySchemeType.HTTP,
            http_scheme="bearer",
        )
        assert scheme.is_api_key is False

    def test_defaults(self) -> None:
        scheme = SecurityScheme(name="s", scheme_type=SecuritySchemeType.OTHER)
        assert scheme.description == ""
        assert scheme.http_scheme is None
        assert scheme.api_key_in is None
        assert scheme.api_key_name is None
        assert scheme.bearer_format is None


# ---------------------------------------------------------------------------
# ToolDefinition
# ---------------------------------------------------------------------------


class TestToolDefinition:
    """Tests for the ToolDefinition dataclass."""

    def _make_tool(self, **kwargs) -> ToolDefinition:  # type: ignore[no-untyped-def]
        """Helper to build a minimal ToolDefinition."""
        defaults = dict(
            name="list_pets",
            description="List all pets",
            http_method="GET",
            path="/pets",
        )
        defaults.update(kwargs)
        return ToolDefinition(**defaults)

    def test_defaults(self) -> None:
        tool = self._make_tool()
        assert tool.parameters == []
        assert tool.request_body is None
        assert tool.security_schemes == []
        assert tool.tags == []
        assert tool.operation_id is None
        assert tool.response_schema == {}
        assert tool.base_url == ""
        assert tool.deprecated is False

    def test_path_parameters(self) -> None:
        path_param = ToolParameter(name="petId", location=ParameterLocation.PATH, required=True)
        query_param = ToolParameter(name="limit", location=ParameterLocation.QUERY)
        tool = self._make_tool(parameters=[path_param, query_param])
        assert tool.path_parameters == [path_param]
        assert query_param not in tool.path_parameters

    def test_query_parameters(self) -> None:
        path_param = ToolParameter(name="petId", location=ParameterLocation.PATH)
        query_param = ToolParameter(name="limit", location=ParameterLocation.QUERY)
        tool = self._make_tool(parameters=[path_param, query_param])
        assert tool.query_parameters == [query_param]

    def test_header_parameters(self) -> None:
        header_param = ToolParameter(name="X-Trace-Id", location=ParameterLocation.HEADER)
        tool = self._make_tool(parameters=[header_param])
        assert tool.header_parameters == [header_param]

    def test_required_parameters(self) -> None:
        req = ToolParameter(name="id", location=ParameterLocation.PATH, required=True)
        opt = ToolParameter(name="limit", location=ParameterLocation.QUERY, required=False)
        tool = self._make_tool(parameters=[req, opt])
        assert tool.required_parameters == [req]

    def test_has_body_false(self) -> None:
        tool = self._make_tool()
        assert tool.has_body is False

    def test_has_body_true(self) -> None:
        body = RequestBody(required=True)
        tool = self._make_tool(request_body=body)
        assert tool.has_body is True

    def test_requires_auth_false(self) -> None:
        tool = self._make_tool()
        assert tool.requires_auth is False

    def test_requires_auth_true(self) -> None:
        scheme = SecurityScheme(
            name="bearerAuth",
            scheme_type=SecuritySchemeType.HTTP,
            http_scheme="bearer",
        )
        tool = self._make_tool(security_schemes=[scheme])
        assert tool.requires_auth is True

    # ------------------------------------------------------------------
    # input_schema tests
    # ------------------------------------------------------------------

    def test_input_schema_empty(self) -> None:
        """A tool with no params and no body should yield an empty object schema."""
        tool = self._make_tool()
        schema = tool.input_schema
        assert schema["type"] == "object"
        assert schema["properties"] == {}
        assert "required" not in schema

    def test_input_schema_with_required_param(self) -> None:
        req = ToolParameter(
            name="petId",
            location=ParameterLocation.PATH,
            required=True,
            schema={"type": "integer"},
        )
        tool = self._make_tool(parameters=[req])
        schema = tool.input_schema
        assert "petId" in schema["properties"]
        assert schema["properties"]["petId"]["type"] == "integer"
        assert "petId" in schema["required"]

    def test_input_schema_with_optional_param(self) -> None:
        opt = ToolParameter(
            name="limit",
            location=ParameterLocation.QUERY,
            required=False,
            schema={"type": "integer"},
        )
        tool = self._make_tool(parameters=[opt])
        schema = tool.input_schema
        assert "limit" in schema["properties"]
        assert "required" not in schema

    def test_input_schema_merges_body_fields(self) -> None:
        """Body fields should appear alongside parameter properties."""
        body_field = RequestBodyField(
            name="name",
            required=True,
            schema={"type": "string"},
        )
        body = RequestBody(required=True, fields=[body_field])
        param = ToolParameter(
            name="limit",
            location=ParameterLocation.QUERY,
            schema={"type": "integer"},
        )
        tool = self._make_tool(parameters=[param], request_body=body)
        schema = tool.input_schema
        assert "limit" in schema["properties"]
        assert "name" in schema["properties"]
        assert "name" in schema["required"]
        assert "limit" not in schema.get("required", [])

    def test_input_schema_non_object_body_becomes_body_param(self) -> None:
        """When the body has no fields, it should be exposed as a single 'body' property."""
        body = RequestBody(
            required=True,
            schema={"type": "string"},
            fields=[],
            description="Raw payload",
        )
        tool = self._make_tool(request_body=body)
        schema = tool.input_schema
        assert "body" in schema["properties"]
        assert schema["properties"]["body"]["type"] == "string"
        assert schema["properties"]["body"]["description"] == "Raw payload"
        assert "body" in schema["required"]

    def test_input_schema_non_object_optional_body_not_in_required(self) -> None:
        """An optional non-object body should not appear in 'required'."""
        body = RequestBody(
            required=False,
            schema={"type": "object"},
            fields=[],
        )
        tool = self._make_tool(request_body=body)
        schema = tool.input_schema
        assert "body" in schema["properties"]
        assert "required" not in schema

    def test_input_schema_body_empty_schema_no_body_param(self) -> None:
        """When body schema is empty and fields is empty, no 'body' key is added."""
        body = RequestBody(required=True, schema={}, fields=[])
        tool = self._make_tool(request_body=body)
        schema = tool.input_schema
        assert "body" not in schema["properties"]

    def test_mutable_defaults_are_independent(self) -> None:
        """Two ToolDefinition instances must not share mutable default containers."""
        t1 = self._make_tool()
        t2 = self._make_tool()
        t1.parameters.append(
            ToolParameter(name="x", location=ParameterLocation.QUERY)
        )
        assert len(t2.parameters) == 0

    def test_repr_contains_name_and_path(self) -> None:
        tool = self._make_tool()
        r = repr(tool)
        assert "list_pets" in r
        assert "/pets" in r


# ---------------------------------------------------------------------------
# ParameterLocation enum
# ---------------------------------------------------------------------------


class TestParameterLocation:
    """Basic sanity checks for the ParameterLocation enum."""

    def test_values(self) -> None:
        assert ParameterLocation.QUERY == "query"
        assert ParameterLocation.HEADER == "header"
        assert ParameterLocation.PATH == "path"
        assert ParameterLocation.COOKIE == "cookie"

    def test_is_str_subclass(self) -> None:
        assert isinstance(ParameterLocation.QUERY, str)


# ---------------------------------------------------------------------------
# SecuritySchemeType enum
# ---------------------------------------------------------------------------


class TestSecuritySchemeType:
    """Basic sanity checks for the SecuritySchemeType enum."""

    def test_values(self) -> None:
        assert SecuritySchemeType.API_KEY == "apiKey"
        assert SecuritySchemeType.HTTP == "http"
        assert SecuritySchemeType.OAUTH2 == "oauth2"
        assert SecuritySchemeType.OPENID_CONNECT == "openIdConnect"
        assert SecuritySchemeType.OTHER == "other"
