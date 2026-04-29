"""Core data models for mcp_forge.

This module defines the internal representation of a parsed OpenAPI endpoint
as a :class:`ToolDefinition` dataclass, along with related types for
parameters, request bodies, and security schemes.

These models form the contract between the parser (:mod:`mcp_forge.parser`)
and the generator (:mod:`mcp_forge.generator`), keeping both sides decoupled
from raw OpenAPI data structures.

Typical usage::

    from mcp_forge.models import ToolDefinition, ToolParameter, SecurityScheme
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ParameterLocation(str, Enum):
    """Where an HTTP parameter is transmitted.

    Corresponds directly to the OpenAPI ``in`` field values.
    """

    QUERY = "query"
    HEADER = "header"
    PATH = "path"
    COOKIE = "cookie"


class SecuritySchemeType(str, Enum):
    """Recognised OpenAPI security scheme types.

    Only the subset that mcp_forge actively scaffolds is enumerated here;
    unknown types are represented as :attr:`OTHER`.
    """

    API_KEY = "apiKey"
    HTTP = "http"           # includes Bearer token
    OAUTH2 = "oauth2"
    OPENID_CONNECT = "openIdConnect"
    OTHER = "other"


@dataclass
class ToolParameter:
    """Represents a single parameter for an MCP tool (maps to an OpenAPI parameter).

    Attributes
    ----------
    name:
        The parameter name as it appears in the OpenAPI spec.
    location:
        Where the parameter is sent: path, query, header, or cookie.
    description:
        Human-readable description of the parameter, or an empty string if
        none was provided in the spec.
    required:
        Whether the parameter is mandatory.
    schema:
        The JSON Schema object describing the parameter's type and constraints.
        Defaults to ``{"type": "string"}`` when the spec omits a schema.
    example:
        Optional example value extracted from the spec.
    """

    name: str
    location: ParameterLocation
    description: str = ""
    required: bool = False
    schema: dict[str, Any] = field(default_factory=lambda: {"type": "string"})
    example: Optional[Any] = None

    def to_json_schema_property(self) -> dict[str, Any]:
        """Return a JSON Schema property dict suitable for embedding in a tool's inputSchema.

        The returned dict merges the parameter's own schema with its description
        so that MCP clients can display helpful documentation.

        Returns
        -------
        dict[str, Any]
            A JSON Schema property object.
        """
        prop: dict[str, Any] = dict(self.schema)
        if self.description:
            prop["description"] = self.description
        if self.example is not None:
            prop["examples"] = [self.example]
        return prop


@dataclass
class RequestBodyField:
    """Describes a single field within a request body.

    When a request body schema is an object, each property is represented as a
    :class:`RequestBodyField` so templates can render typed input fields.

    Attributes
    ----------
    name:
        Property name within the request body object.
    description:
        Human-readable description, or empty string.
    required:
        Whether this field is listed under the schema's ``required`` array.
    schema:
        The JSON Schema object for this field.
    """

    name: str
    description: str = ""
    required: bool = False
    schema: dict[str, Any] = field(default_factory=lambda: {"type": "string"})

    def to_json_schema_property(self) -> dict[str, Any]:
        """Return a JSON Schema property dict for this request body field.

        Returns
        -------
        dict[str, Any]
            A JSON Schema property object.
        """
        prop: dict[str, Any] = dict(self.schema)
        if self.description:
            prop["description"] = self.description
        return prop


@dataclass
class RequestBody:
    """Represents the request body of an OpenAPI operation.

    Attributes
    ----------
    description:
        Human-readable description of the request body.
    required:
        Whether the body is required by the operation.
    content_type:
        The primary MIME type (e.g. ``"application/json"``).
    schema:
        The raw JSON Schema dict for the entire body.
    fields:
        A flat list of :class:`RequestBodyField` objects extracted from the
        schema's ``properties`` when the schema type is ``"object"``.
        Empty when the body schema is not an object or has no properties.
    """

    description: str = ""
    required: bool = False
    content_type: str = "application/json"
    schema: dict[str, Any] = field(default_factory=dict)
    fields: list[RequestBodyField] = field(default_factory=list)


@dataclass
class SecurityScheme:
    """Represents a security scheme declared in the OpenAPI spec.

    Attributes
    ----------
    name:
        The key under which the scheme is registered in
        ``components/securitySchemes``.
    scheme_type:
        The :class:`SecuritySchemeType` (``apiKey``, ``http``, etc.).
    description:
        Human-readable description, or empty string.
    http_scheme:
        For ``http`` type schemes, the scheme name (e.g. ``"bearer"``,
        ``"basic"``).
    api_key_in:
        For ``apiKey`` schemes, where the key is passed
        (``"header"``, ``"query"``, or ``"cookie"``).
    api_key_name:
        For ``apiKey`` schemes, the name of the header / query parameter.
    bearer_format:
        Optional hint about the bearer token format (e.g. ``"JWT"``).
    """

    name: str
    scheme_type: SecuritySchemeType
    description: str = ""
    http_scheme: Optional[str] = None       # e.g. "bearer", "basic"
    api_key_in: Optional[str] = None        # "header", "query", "cookie"
    api_key_name: Optional[str] = None
    bearer_format: Optional[str] = None

    @property
    def is_bearer(self) -> bool:
        """Return ``True`` when this scheme uses a Bearer token."""
        return (
            self.scheme_type == SecuritySchemeType.HTTP
            and isinstance(self.http_scheme, str)
            and self.http_scheme.lower() == "bearer"
        )

    @property
    def is_api_key(self) -> bool:
        """Return ``True`` when this scheme uses an API key."""
        return self.scheme_type == SecuritySchemeType.API_KEY


@dataclass
class ToolDefinition:
    """Internal representation of a single OpenAPI operation as an MCP tool.

    Every field that a Jinja2 template might need is stored here so that
    templates never have to import or understand OpenAPI structures directly.

    Attributes
    ----------
    name:
        Unique tool name derived from the ``operationId`` or synthesised from
        the HTTP method and path (e.g. ``"get_pets"``).  MCP clients use this
        as the tool identifier.
    description:
        Human-readable description taken from the operation's ``summary`` and/or
        ``description`` fields.
    http_method:
        Uppercase HTTP verb: ``"GET"``, ``"POST"``, ``"PUT"``, ``"PATCH"``,
        ``"DELETE"``, etc.
    path:
        The API path exactly as written in the spec (e.g. ``"/pets/{petId}"``).
    parameters:
        Ordered list of :class:`ToolParameter` objects (path, query, header,
        cookie parameters).
    request_body:
        The :class:`RequestBody` for this operation, or ``None`` if the
        operation accepts no body.
    security_schemes:
        List of :class:`SecurityScheme` objects that apply to this operation
        (resolved from both operation-level and global security requirements).
    tags:
        OpenAPI tags associated with the operation, used for grouping.
    operation_id:
        The raw ``operationId`` string from the spec, or ``None`` if absent.
    response_schema:
        JSON Schema dict of the primary successful response (200/201), or an
        empty dict when no response schema is defined.
    base_url:
        The base URL from the first ``servers`` entry, or empty string.
    deprecated:
        ``True`` when the operation is marked as deprecated in the spec.
    """

    name: str
    description: str
    http_method: str
    path: str
    parameters: list[ToolParameter] = field(default_factory=list)
    request_body: Optional[RequestBody] = None
    security_schemes: list[SecurityScheme] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    operation_id: Optional[str] = None
    response_schema: dict[str, Any] = field(default_factory=dict)
    base_url: str = ""
    deprecated: bool = False

    # ------------------------------------------------------------------
    # Convenience properties used by templates
    # ------------------------------------------------------------------

    @property
    def path_parameters(self) -> list[ToolParameter]:
        """Return only the path parameters for this tool."""
        return [
            p for p in self.parameters
            if p.location == ParameterLocation.PATH
        ]

    @property
    def query_parameters(self) -> list[ToolParameter]:
        """Return only the query parameters for this tool."""
        return [
            p for p in self.parameters
            if p.location == ParameterLocation.QUERY
        ]

    @property
    def header_parameters(self) -> list[ToolParameter]:
        """Return only the header parameters for this tool."""
        return [
            p for p in self.parameters
            if p.location == ParameterLocation.HEADER
        ]

    @property
    def required_parameters(self) -> list[ToolParameter]:
        """Return all required parameters (any location)."""
        return [p for p in self.parameters if p.required]

    @property
    def has_body(self) -> bool:
        """Return ``True`` when the operation accepts a request body."""
        return self.request_body is not None

    @property
    def requires_auth(self) -> bool:
        """Return ``True`` when at least one security scheme is attached."""
        return len(self.security_schemes) > 0

    @property
    def input_schema(self) -> dict[str, Any]:
        """Return a JSON Schema ``object`` describing all tool inputs.

        The schema merges path/query parameters *and* request body fields into
        a single flat ``properties`` mapping, which is what MCP clients expect
        for the ``inputSchema`` field of a tool definition.

        Returns
        -------
        dict[str, Any]
            A JSON Schema object with ``type``, ``properties``, and
            ``required`` keys.
        """
        properties: dict[str, Any] = {}
        required_names: list[str] = []

        for param in self.parameters:
            properties[param.name] = param.to_json_schema_property()
            if param.required:
                required_names.append(param.name)

        if self.request_body is not None:
            for body_field in self.request_body.fields:
                properties[body_field.name] = body_field.to_json_schema_property()
                if body_field.required:
                    required_names.append(body_field.name)
            # If there are no named fields (e.g. non-object schema), expose
            # the whole body as a single ``body`` parameter.
            if not self.request_body.fields and self.request_body.schema:
                body_prop: dict[str, Any] = dict(self.request_body.schema)
                if self.request_body.description:
                    body_prop["description"] = self.request_body.description
                properties["body"] = body_prop
                if self.request_body.required:
                    required_names.append("body")

        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required_names:
            schema["required"] = required_names
        return schema

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"ToolDefinition(name={self.name!r}, "
            f"method={self.http_method}, path={self.path!r})"
        )
