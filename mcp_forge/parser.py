"""Parse an OpenAPI 3.x spec dict into a list of ToolDefinition objects.

This module forms the internal contract between the loader and the generator:
it translates raw OpenAPI data structures into the project's canonical
:class:`~mcp_forge.models.ToolDefinition` dataclass so that templates remain
decoupled from OpenAPI specifics.

Public API::

    tool_defs = parse_spec(spec_dict)

The parser handles:

* **Path parameters** – parameters declared at path-item level are inherited
  by every operation under that path.
* **Operation parameters** – merged with (and overriding) path-level params.
* **Request bodies** – the primary content type is resolved; object schemas
  have their properties expanded into :class:`~mcp_forge.models.RequestBodyField`
  objects.
* **Security schemes** – both global and operation-level ``security``
  requirements are resolved against ``components/securitySchemes``.
* **$ref resolution** – simple ``$ref`` pointers of the form
  ``#/components/...`` are resolved inline; circular or external refs are
  left as-is rather than crashing.
* **Base URL** – taken from the first ``servers`` entry, falling back to
  an empty string.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from mcp_forge.models import (
    ParameterLocation,
    RequestBody,
    RequestBodyField,
    SecurityScheme,
    SecuritySchemeType,
    ToolDefinition,
    ToolParameter,
)

# HTTP methods that OpenAPI treats as operations on a path item.
_HTTP_METHODS = frozenset(
    ["get", "put", "post", "delete", "options", "head", "patch", "trace"]
)


class ParserError(Exception):
    """Raised when the OpenAPI spec cannot be parsed into ToolDefinitions.

    This is typically triggered by structural issues that passed the loader's
    validation but are too malformed for the parser to handle gracefully.
    """


def parse_spec(spec: dict[str, Any]) -> list[ToolDefinition]:
    """Parse *spec* and return a list of :class:`~mcp_forge.models.ToolDefinition` objects.

    Each OpenAPI operation (``GET /pets``, ``POST /pets``, etc.) becomes one
    :class:`~mcp_forge.models.ToolDefinition`.  Operations are yielded in the
    order they appear in the ``paths`` mapping.

    Parameters
    ----------
    spec:
        Parsed OpenAPI 3.x spec dictionary as returned by
        :func:`mcp_forge.loader.load_spec`.

    Returns
    -------
    list[ToolDefinition]
        One entry per discovered OpenAPI operation.  An empty list is returned
        when the spec has no ``paths`` or when all path items are empty.

    Raises
    ------
    ParserError
        If the spec structure is so malformed that iteration cannot continue
        (e.g. ``paths`` is not a dict).
    """
    paths = spec.get("paths", {})
    if paths is None:
        paths = {}
    if not isinstance(paths, dict):
        raise ParserError(
            f"'paths' must be a mapping, got {type(paths).__name__!r}."
        )

    # Resolve global security requirements once; used as the fallback when an
    # operation does not declare its own security.
    global_security: list[dict[str, Any]] = spec.get("security") or []
    security_schemes_map = _extract_security_schemes_map(spec)
    base_url = _extract_base_url(spec)

    tool_definitions: list[ToolDefinition] = []
    seen_names: set[str] = set()

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue

        # Resolve path-item-level $ref (uncommon but valid in OpenAPI 3.x).
        path_item = _resolve_ref(path_item, spec)

        # Parameters declared at path-item level are inherited by all
        # operations under this path unless overridden.
        path_level_params: list[dict[str, Any]] = _resolve_param_list(
            path_item.get("parameters", []), spec
        )

        for method in _HTTP_METHODS:
            operation = path_item.get(method)
            if operation is None:
                continue
            if not isinstance(operation, dict):
                continue

            tool = _parse_operation(
                path=path,
                method=method,
                operation=operation,
                path_level_params=path_level_params,
                global_security=global_security,
                security_schemes_map=security_schemes_map,
                base_url=base_url,
                spec=spec,
                seen_names=seen_names,
            )
            tool_definitions.append(tool)

    return tool_definitions


# ---------------------------------------------------------------------------
# Operation parsing
# ---------------------------------------------------------------------------


def _parse_operation(
    *,
    path: str,
    method: str,
    operation: dict[str, Any],
    path_level_params: list[dict[str, Any]],
    global_security: list[dict[str, Any]],
    security_schemes_map: dict[str, SecurityScheme],
    base_url: str,
    spec: dict[str, Any],
    seen_names: set[str],
) -> ToolDefinition:
    """Convert a single OpenAPI operation dict into a :class:`ToolDefinition`.

    Parameters
    ----------
    path:
        The OpenAPI path string, e.g. ``"/pets/{petId}"``.
    method:
        Lowercase HTTP method string, e.g. ``"get"``.
    operation:
        The OpenAPI operation object dict.
    path_level_params:
        Parameters declared at the path-item level (inherited by this op).
    global_security:
        The global ``security`` requirement list from the spec root.
    security_schemes_map:
        Mapping from scheme name to resolved :class:`SecurityScheme`.
    base_url:
        Base URL string from the first ``servers`` entry.
    spec:
        Full spec dict (needed for ``$ref`` resolution).
    seen_names:
        Mutable set of tool names already assigned; used to de-duplicate.

    Returns
    -------
    ToolDefinition
        Fully populated tool definition.
    """
    operation_id: Optional[str] = operation.get("operationId")
    name = _derive_tool_name(method, path, operation_id, seen_names)
    seen_names.add(name)

    summary: str = operation.get("summary") or ""
    description_raw: str = operation.get("description") or ""
    description = summary if summary else description_raw
    if summary and description_raw and description_raw != summary:
        description = f"{summary}. {description_raw}"

    tags: list[str] = operation.get("tags") or []
    deprecated: bool = bool(operation.get("deprecated", False))

    # Merge path-level and operation-level parameters; operation params win.
    op_params_raw = _resolve_param_list(operation.get("parameters", []), spec)
    parameters = _merge_parameters(path_level_params, op_params_raw, spec)
    tool_params = [_parse_parameter(p) for p in parameters]

    # Request body
    request_body: Optional[RequestBody] = None
    if "requestBody" in operation:
        rb_raw = _resolve_ref(operation["requestBody"], spec)
        request_body = _parse_request_body(rb_raw, spec)

    # Security schemes
    op_security = operation.get("security")
    effective_security: list[dict[str, Any]]
    if op_security is not None:
        # Operation-level security overrides global (an empty list means
        # the operation explicitly requires no auth).
        effective_security = op_security
    else:
        effective_security = global_security

    resolved_schemes = _resolve_security_schemes(
        effective_security, security_schemes_map
    )

    # Response schema (first 2xx response)
    response_schema = _extract_response_schema(operation.get("responses", {}), spec)

    return ToolDefinition(
        name=name,
        description=description,
        http_method=method.upper(),
        path=path,
        parameters=tool_params,
        request_body=request_body,
        security_schemes=resolved_schemes,
        tags=tags,
        operation_id=operation_id,
        response_schema=response_schema,
        base_url=base_url,
        deprecated=deprecated,
    )


# ---------------------------------------------------------------------------
# Tool name derivation
# ---------------------------------------------------------------------------


def _derive_tool_name(
    method: str,
    path: str,
    operation_id: Optional[str],
    seen_names: set[str],
) -> str:
    """Derive a unique, slug-safe tool name for an operation.

    Prefers ``operationId`` when present (after sanitisation).  Falls back to
    a ``{method}_{path_slug}`` pattern when ``operationId`` is absent or
    produces a duplicate.

    Parameters
    ----------
    method:
        Lowercase HTTP method.
    path:
        OpenAPI path string.
    operation_id:
        Raw ``operationId`` value from the spec, or ``None``.
    seen_names:
        Set of names already used; used to append a numeric suffix on clash.

    Returns
    -------
    str
        A snake_case identifier safe for use as a Python / JavaScript function
        name and as an MCP tool name.
    """
    if operation_id:
        candidate = _slugify(operation_id)
    else:
        candidate = _slugify(f"{method}_{path}")

    # Ensure uniqueness by appending an integer suffix when needed.
    final = candidate
    counter = 2
    while final in seen_names:
        final = f"{candidate}_{counter}"
        counter += 1
    return final


def _slugify(text: str) -> str:
    """Convert *text* to a lowercase snake_case identifier.

    1. Replaces path separators and curly braces with underscores.
    2. Replaces non-alphanumeric characters with underscores.
    3. Collapses consecutive underscores.
    4. Strips leading/trailing underscores.
    5. Prefixes with ``op_`` when the result starts with a digit.

    Parameters
    ----------
    text:
        Arbitrary string to slugify.

    Returns
    -------
    str
        Safe identifier string.
    """
    # Replace common OpenAPI separators with underscores.
    slug = text.replace("/", "_").replace("-", "_").replace("{", "").replace("}", "")
    # Replace any remaining non-alphanumeric chars with underscores.
    slug = re.sub(r"[^\w]", "_", slug)
    # Collapse runs of underscores.
    slug = re.sub(r"_+", "_", slug)
    slug = slug.strip("_").lower()
    if not slug:
        slug = "operation"
    # Identifiers must not start with a digit.
    if slug[0].isdigit():
        slug = f"op_{slug}"
    return slug


# ---------------------------------------------------------------------------
# Parameter parsing
# ---------------------------------------------------------------------------


def _resolve_param_list(
    params_raw: list[Any], spec: dict[str, Any]
) -> list[dict[str, Any]]:
    """Resolve a list of parameter objects or ``$ref`` pointers.

    Parameters
    ----------
    params_raw:
        List of raw parameter dicts or ``{"$ref": "..."}`` objects.
    spec:
        Full spec dict for ``$ref`` resolution.

    Returns
    -------
    list[dict[str, Any]]
        List of resolved parameter dicts.
    """
    resolved: list[dict[str, Any]] = []
    for item in params_raw:
        if not isinstance(item, dict):
            continue
        item = _resolve_ref(item, spec)
        if isinstance(item, dict):
            resolved.append(item)
    return resolved


def _merge_parameters(
    path_level: list[dict[str, Any]],
    op_level: list[dict[str, Any]],
    spec: dict[str, Any],
) -> list[dict[str, Any]]:
    """Merge path-level and operation-level parameters.

    Operation-level parameters override path-level parameters that share the
    same ``(name, in)`` pair, per the OpenAPI spec.

    Parameters
    ----------
    path_level:
        Parameters declared at path-item level.
    op_level:
        Parameters declared at operation level.
    spec:
        Full spec dict (unused here, reserved for future deep-ref resolution).

    Returns
    -------
    list[dict[str, Any]]
        Merged, de-duplicated parameter list.
    """
    # Index path-level params by (name, in).
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for param in path_level:
        key = (param.get("name", ""), param.get("in", ""))
        merged[key] = param
    # Operation params override.
    for param in op_level:
        key = (param.get("name", ""), param.get("in", ""))
        merged[key] = param
    return list(merged.values())


def _parse_parameter(param: dict[str, Any]) -> ToolParameter:
    """Convert a resolved OpenAPI parameter object to a :class:`ToolParameter`.

    Parameters
    ----------
    param:
        Resolved (``$ref``-free) OpenAPI parameter dict.

    Returns
    -------
    ToolParameter
        Populated parameter object.
    """
    name: str = param.get("name") or ""
    in_raw: str = param.get("in") or "query"

    try:
        location = ParameterLocation(in_raw.lower())
    except ValueError:
        location = ParameterLocation.QUERY

    description: str = param.get("description") or ""
    required: bool = bool(param.get("required", False))
    # Path parameters are always required per OpenAPI spec.
    if location == ParameterLocation.PATH:
        required = True

    schema: dict[str, Any] = param.get("schema") or {"type": "string"}
    example: Any = param.get("example")
    if example is None:
        example = schema.get("example")

    return ToolParameter(
        name=name,
        location=location,
        description=description,
        required=required,
        schema=schema,
        example=example,
    )


# ---------------------------------------------------------------------------
# Request body parsing
# ---------------------------------------------------------------------------


def _parse_request_body(
    rb_raw: dict[str, Any], spec: dict[str, Any]
) -> RequestBody:
    """Convert a resolved OpenAPI requestBody object to a :class:`RequestBody`.

    Selects the primary content type using the following priority:
    ``application/json`` > ``application/x-www-form-urlencoded`` >
    ``multipart/form-data`` > first available.

    Parameters
    ----------
    rb_raw:
        Resolved (``$ref``-free) OpenAPI requestBody dict.
    spec:
        Full spec dict for nested ``$ref`` resolution.

    Returns
    -------
    RequestBody
        Populated request body object.
    """
    description: str = rb_raw.get("description") or ""
    required: bool = bool(rb_raw.get("required", False))
    content: dict[str, Any] = rb_raw.get("content") or {}

    # Select preferred content type.
    content_type = _pick_content_type(content)
    schema: dict[str, Any] = {}
    fields: list[RequestBodyField] = []

    if content_type and content_type in content:
        media_object = content[content_type]
        raw_schema = media_object.get("schema") or {}
        schema = _resolve_ref(raw_schema, spec)
        if not isinstance(schema, dict):
            schema = {}
        # Expand top-level object properties into RequestBodyField list.
        fields = _extract_body_fields(schema, spec)

    return RequestBody(
        description=description,
        required=required,
        content_type=content_type or "application/json",
        schema=schema,
        fields=fields,
    )


def _pick_content_type(content: dict[str, Any]) -> Optional[str]:
    """Return the preferred content type key from a ``content`` mapping.

    Parameters
    ----------
    content:
        The ``content`` dict from an OpenAPI requestBody or response.

    Returns
    -------
    str or None
        The chosen content type key, or ``None`` when ``content`` is empty.
    """
    preferred = [
        "application/json",
        "application/x-www-form-urlencoded",
        "multipart/form-data",
    ]
    for ct in preferred:
        if ct in content:
            return ct
    # Fall back to the first available key.
    return next(iter(content), None)


def _extract_body_fields(
    schema: dict[str, Any], spec: dict[str, Any]
) -> list[RequestBodyField]:
    """Extract a flat list of :class:`RequestBodyField` from an object schema.

    Only works when the schema's ``type`` is ``"object"`` or when there is a
    ``properties`` mapping present.  Returns an empty list for all other schema
    shapes (arrays, primitives, ``oneOf``/``anyOf`` compositions, etc.).

    Parameters
    ----------
    schema:
        Resolved JSON Schema object.
    spec:
        Full spec dict for nested ``$ref`` resolution.

    Returns
    -------
    list[RequestBodyField]
        One entry per property in ``schema.properties``.
    """
    schema_type = schema.get("type")
    properties: dict[str, Any] = schema.get("properties") or {}

    if not properties and schema_type not in ("object", None):
        return []

    required_fields: list[str] = schema.get("required") or []
    fields: list[RequestBodyField] = []

    for prop_name, prop_schema_raw in properties.items():
        prop_schema = _resolve_ref(prop_schema_raw, spec)
        if not isinstance(prop_schema, dict):
            prop_schema = {"type": "string"}
        field_desc: str = prop_schema.get("description") or ""
        field_required = prop_name in required_fields
        fields.append(
            RequestBodyField(
                name=prop_name,
                description=field_desc,
                required=field_required,
                schema=prop_schema,
            )
        )

    return fields


# ---------------------------------------------------------------------------
# Security scheme extraction and resolution
# ---------------------------------------------------------------------------


def _extract_security_schemes_map(
    spec: dict[str, Any],
) -> dict[str, SecurityScheme]:
    """Build a mapping from scheme name to :class:`SecurityScheme` from the spec.

    Reads ``components/securitySchemes`` and converts each entry.

    Parameters
    ----------
    spec:
        Full parsed OpenAPI spec dict.

    Returns
    -------
    dict[str, SecurityScheme]
        Mapping from scheme name (e.g. ``"bearerAuth"``) to a
        :class:`SecurityScheme` instance.  Returns an empty dict when the spec
        declares no security schemes.
    """
    components = spec.get("components") or {}
    raw_schemes: dict[str, Any] = components.get("securitySchemes") or {}
    result: dict[str, SecurityScheme] = {}

    for scheme_name, scheme_raw in raw_schemes.items():
        scheme_raw = _resolve_ref(scheme_raw, spec)
        if not isinstance(scheme_raw, dict):
            continue
        result[scheme_name] = _parse_security_scheme(scheme_name, scheme_raw)

    return result


def _parse_security_scheme(
    name: str, raw: dict[str, Any]
) -> SecurityScheme:
    """Convert a raw OpenAPI security scheme dict to a :class:`SecurityScheme`.

    Parameters
    ----------
    name:
        The key under which this scheme is registered in
        ``components/securitySchemes``.
    raw:
        Resolved security scheme dict.

    Returns
    -------
    SecurityScheme
        Populated security scheme object.
    """
    type_raw: str = (raw.get("type") or "").strip()
    try:
        scheme_type = SecuritySchemeType(type_raw)
    except ValueError:
        scheme_type = SecuritySchemeType.OTHER

    description: str = raw.get("description") or ""
    http_scheme: Optional[str] = raw.get("scheme")  # "bearer", "basic", …
    bearer_format: Optional[str] = raw.get("bearerFormat")
    api_key_in: Optional[str] = raw.get("in")  # "header", "query", "cookie"
    api_key_name: Optional[str] = raw.get("name")

    return SecurityScheme(
        name=name,
        scheme_type=scheme_type,
        description=description,
        http_scheme=http_scheme,
        api_key_in=api_key_in,
        api_key_name=api_key_name,
        bearer_format=bearer_format,
    )


def _resolve_security_schemes(
    security_requirements: list[dict[str, Any]],
    schemes_map: dict[str, SecurityScheme],
) -> list[SecurityScheme]:
    """Resolve a list of security requirement objects to :class:`SecurityScheme` instances.

    Each security requirement is a ``{scheme_name: [scopes]}`` mapping.  Only
    schemes that exist in *schemes_map* are returned; unknown names are silently
    skipped.

    Parameters
    ----------
    security_requirements:
        The ``security`` list from either the spec root or an operation.
    schemes_map:
        Pre-built mapping from scheme name to :class:`SecurityScheme`.

    Returns
    -------
    list[SecurityScheme]
        De-duplicated list of matching security schemes in declaration order.
    """
    seen: set[str] = set()
    schemes: list[SecurityScheme] = []
    for requirement in security_requirements:
        if not isinstance(requirement, dict):
            continue
        for scheme_name in requirement.keys():
            if scheme_name in schemes_map and scheme_name not in seen:
                schemes.append(schemes_map[scheme_name])
                seen.add(scheme_name)
    return schemes


# ---------------------------------------------------------------------------
# Response schema extraction
# ---------------------------------------------------------------------------


def _extract_response_schema(
    responses: dict[str, Any], spec: dict[str, Any]
) -> dict[str, Any]:
    """Extract the JSON Schema of the primary successful response.

    Iterates over 2xx status codes in ascending order and returns the schema
    of the first one that has a JSON content body.  Falls back to an empty
    dict when nothing suitable is found.

    Parameters
    ----------
    responses:
        The ``responses`` mapping from an OpenAPI operation.
    spec:
        Full spec dict for ``$ref`` resolution.

    Returns
    -------
    dict[str, Any]
        Resolved JSON Schema dict, or ``{}`` when no schema is available.
    """
    if not isinstance(responses, dict):
        return {}

    # Try 200, 201, 202, … 299 in order; also try the "2XX" wildcard.
    candidates: list[str] = []
    for code in sorted(responses.keys()):
        if str(code).startswith("2"):
            candidates.append(str(code))

    for code in candidates:
        response_raw = responses.get(code) or responses.get(int(code))  # type: ignore[call-overload]
        if response_raw is None:
            continue
        response_obj = _resolve_ref(response_raw, spec)
        if not isinstance(response_obj, dict):
            continue
        content = response_obj.get("content") or {}
        ct = _pick_content_type(content)
        if ct and ct in content:
            media = content[ct]
            raw_schema = media.get("schema") or {}
            resolved = _resolve_ref(raw_schema, spec)
            if isinstance(resolved, dict) and resolved:
                return resolved

    return {}


# ---------------------------------------------------------------------------
# $ref resolution
# ---------------------------------------------------------------------------


def _resolve_ref(obj: Any, spec: dict[str, Any]) -> Any:
    """Resolve a JSON ``$ref`` pointer within *spec*.

    Only handles local references of the form ``"#/components/..."`` or any
    ``"#/..."`` path.  Non-local (HTTP) references and circular references are
    returned unchanged to avoid infinite loops or network calls.

    Parameters
    ----------
    obj:
        An object that may be a ``{"$ref": "..."}`` dict, or any other value.
    spec:
        The root spec dict used as the resolution document.

    Returns
    -------
    Any
        The resolved object if the ref was local and resolvable; otherwise
        the original *obj* is returned.
    """
    if not isinstance(obj, dict) or "$ref" not in obj:
        return obj

    ref: str = obj["$ref"]
    if not ref.startswith("#/"):
        # External or URL-based $ref – return original to avoid network calls.
        return obj

    parts = ref[2:].split("/")  # strip leading '#/' then split on '/'
    current: Any = spec
    for part in parts:
        # JSON Pointer escaping: ~1 -> '/', ~0 -> '~'
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return obj  # Can't traverse further – return original.
        if current is None:
            return obj  # Reference target not found.

    # Recursively resolve any nested $ref in the resolved object.
    if isinstance(current, dict) and "$ref" in current:
        return _resolve_ref(current, spec)
    return current


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_base_url(spec: dict[str, Any]) -> str:
    """Return the base URL from the first ``servers`` entry, or empty string.

    Parameters
    ----------
    spec:
        Full parsed OpenAPI spec dict.

    Returns
    -------
    str
        URL string, e.g. ``"https://api.example.com/v1"``, or ``""``.
    """
    servers: list[Any] = spec.get("servers") or []
    if servers and isinstance(servers[0], dict):
        return servers[0].get("url") or ""
    return ""
