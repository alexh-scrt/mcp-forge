"""Unit tests for mcp_forge.loader.

Covers loading from local files (YAML and JSON), loading from remote URLs
(mocked with httpx), validation logic, and all error paths.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml

from mcp_forge.loader import (
    LoaderError,
    _fetch_url,
    _parse_text,
    _read_file,
    _validate_semantic,
    _validate_with_jsonschema,
    load_spec,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).parent / "fixtures"
PETSTORE_YAML = FIXTURE_DIR / "petstore.yaml"


def _minimal_spec(**overrides: Any) -> dict[str, Any]:
    """Return a minimal valid OpenAPI 3.0 spec dict, with optional overrides."""
    spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {},
    }
    spec.update(overrides)
    return spec


# ---------------------------------------------------------------------------
# load_spec – happy paths
# ---------------------------------------------------------------------------


class TestLoadSpecFile:
    """Tests for load_spec reading from the local filesystem."""

    def test_load_petstore_yaml(self) -> None:
        """The bundled petstore fixture must load without errors."""
        spec = load_spec(str(PETSTORE_YAML))
        assert isinstance(spec, dict)
        assert spec["openapi"].startswith("3.")
        assert spec["info"]["title"] == "Petstore"

    def test_load_petstore_has_paths(self) -> None:
        """The petstore fixture must expose /pets and /pets/{petId} paths."""
        spec = load_spec(str(PETSTORE_YAML))
        paths = spec.get("paths", {})
        assert "/pets" in paths
        assert "/pets/{petId}" in paths

    def test_load_petstore_has_components(self) -> None:
        """The petstore fixture must have component schemas."""
        spec = load_spec(str(PETSTORE_YAML))
        schemas = spec.get("components", {}).get("schemas", {})
        assert "Pet" in schemas
        assert "NewPet" in schemas
        assert "Error" in schemas

    def test_load_petstore_has_security_schemes(self) -> None:
        """The petstore fixture must declare bearerAuth and apiKey schemes."""
        spec = load_spec(str(PETSTORE_YAML))
        schemes = spec.get("components", {}).get("securitySchemes", {})
        assert "bearerAuth" in schemes
        assert "apiKey" in schemes

    def test_load_yaml_file(self, tmp_path: Path) -> None:
        """load_spec must parse a YAML file written to a temp directory."""
        content = yaml.dump(_minimal_spec())
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(content, encoding="utf-8")
        spec = load_spec(str(spec_file))
        assert spec["openapi"] == "3.0.3"

    def test_load_json_file(self, tmp_path: Path) -> None:
        """load_spec must parse a JSON file written to a temp directory."""
        content = json.dumps(_minimal_spec())
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(content, encoding="utf-8")
        spec = load_spec(str(spec_file))
        assert spec["openapi"] == "3.0.3"

    def test_returns_dict(self, tmp_path: Path) -> None:
        """load_spec must always return a plain dict."""
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(yaml.dump(_minimal_spec()), encoding="utf-8")
        result = load_spec(str(spec_file))
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# load_spec – URL path (mocked)
# ---------------------------------------------------------------------------


class TestLoadSpecUrl:
    """Tests for load_spec fetching from remote URLs (HTTP responses mocked)."""

    def _mock_response(self, text: str, status_code: int = 200) -> MagicMock:
        """Build a mock httpx.Response-like object."""
        mock_resp = MagicMock()
        mock_resp.text = text
        mock_resp.status_code = status_code
        if status_code >= 400:
            import httpx
            mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                message=f"HTTP {status_code}",
                request=MagicMock(),
                response=mock_resp,
            )
        else:
            mock_resp.raise_for_status.return_value = None
        return mock_resp

    def test_load_from_https_url(self) -> None:
        """load_spec must fetch and parse a spec from an HTTPS URL."""
        spec_content = yaml.dump(_minimal_spec())
        mock_resp = self._mock_response(spec_content)
        with patch("mcp_forge.loader.httpx.get", return_value=mock_resp) as mock_get:
            spec = load_spec("https://example.com/openapi.yaml")
        mock_get.assert_called_once()
        assert spec["openapi"] == "3.0.3"

    def test_load_from_http_url(self) -> None:
        """load_spec must also handle plain http:// URLs."""
        spec_content = json.dumps(_minimal_spec())
        mock_resp = self._mock_response(spec_content)
        with patch("mcp_forge.loader.httpx.get", return_value=mock_resp):
            spec = load_spec("http://example.com/openapi.json")
        assert spec["info"]["title"] == "Test API"

    def test_http_error_raises_loader_error(self) -> None:
        """A 404 response must raise LoaderError."""
        import httpx

        mock_resp = self._mock_response("", status_code=404)
        with patch("mcp_forge.loader.httpx.get", return_value=mock_resp):
            with pytest.raises(LoaderError, match="HTTP 404"):
                load_spec("https://example.com/missing.yaml")

    def test_network_error_raises_loader_error(self) -> None:
        """A network-level error must raise LoaderError with a helpful message."""
        import httpx

        with patch(
            "mcp_forge.loader.httpx.get",
            side_effect=httpx.ConnectError("Connection refused"),
        ):
            with pytest.raises(LoaderError, match="Network error"):
                load_spec("https://example.com/openapi.yaml")

    def test_timeout_raises_loader_error(self) -> None:
        """A timeout must raise LoaderError with a timeout message."""
        import httpx

        with patch(
            "mcp_forge.loader.httpx.get",
            side_effect=httpx.TimeoutException("timed out"),
        ):
            with pytest.raises(LoaderError, match="timed out"):
                load_spec("https://example.com/openapi.yaml")

    def test_url_dispatched_to_fetch_url(self) -> None:
        """load_spec must route URLs through _fetch_url, not _read_file."""
        spec_content = yaml.dump(_minimal_spec())
        mock_resp = self._mock_response(spec_content)
        with patch("mcp_forge.loader.httpx.get", return_value=mock_resp) as mock_get:
            load_spec("https://example.com/spec.yaml")
        # httpx.get should have been called (i.e. URL path taken)
        assert mock_get.called


# ---------------------------------------------------------------------------
# _read_file
# ---------------------------------------------------------------------------


class TestReadFile:
    """Tests for the internal _read_file helper."""

    def test_reads_existing_file(self, tmp_path: Path) -> None:
        f = tmp_path / "api.yaml"
        f.write_text("hello", encoding="utf-8")
        assert _read_file(str(f)) == "hello"

    def test_missing_file_raises_loader_error(self) -> None:
        with pytest.raises(LoaderError, match="not found"):
            _read_file("/definitely/does/not/exist/spec.yaml")

    def test_directory_raises_loader_error(self, tmp_path: Path) -> None:
        with pytest.raises(LoaderError, match="not a file"):
            _read_file(str(tmp_path))

    def test_returns_full_content(self, tmp_path: Path) -> None:
        content = "line1\nline2\nline3"
        f = tmp_path / "spec.txt"
        f.write_text(content, encoding="utf-8")
        assert _read_file(str(f)) == content


# ---------------------------------------------------------------------------
# _fetch_url
# ---------------------------------------------------------------------------


class TestFetchUrl:
    """Tests for the internal _fetch_url helper."""

    def test_returns_response_text(self) -> None:
        mock_resp = MagicMock()
        mock_resp.text = "spec content"
        mock_resp.raise_for_status.return_value = None
        with patch("mcp_forge.loader.httpx.get", return_value=mock_resp):
            result = _fetch_url("https://example.com/spec.yaml")
        assert result == "spec content"

    def test_follows_redirects(self) -> None:
        mock_resp = MagicMock()
        mock_resp.text = "ok"
        mock_resp.raise_for_status.return_value = None
        with patch("mcp_forge.loader.httpx.get", return_value=mock_resp) as mock_get:
            _fetch_url("https://example.com/spec.yaml")
        call_kwargs = mock_get.call_args.kwargs
        assert call_kwargs.get("follow_redirects") is True

    def test_timeout_set(self) -> None:
        mock_resp = MagicMock()
        mock_resp.text = "ok"
        mock_resp.raise_for_status.return_value = None
        with patch("mcp_forge.loader.httpx.get", return_value=mock_resp) as mock_get:
            _fetch_url("https://example.com/spec.yaml")
        call_kwargs = mock_get.call_args.kwargs
        assert call_kwargs.get("timeout") == 30.0

    def test_http_status_error_raises_loader_error(self) -> None:
        import httpx

        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message="Service unavailable",
            request=MagicMock(),
            response=mock_resp,
        )
        with patch("mcp_forge.loader.httpx.get", return_value=mock_resp):
            with pytest.raises(LoaderError, match="503"):
                _fetch_url("https://example.com/spec.yaml")


# ---------------------------------------------------------------------------
# _parse_text
# ---------------------------------------------------------------------------


class TestParseText:
    """Tests for the internal _parse_text helper."""

    def test_parses_yaml(self) -> None:
        text = yaml.dump({"openapi": "3.0.0", "info": {"title": "T", "version": "1"}})
        result = _parse_text(text, "test")
        assert result["openapi"] == "3.0.0"

    def test_parses_json(self) -> None:
        text = json.dumps({"openapi": "3.0.0", "info": {"title": "T", "version": "1"}})
        result = _parse_text(text, "test.json")
        assert result["openapi"] == "3.0.0"

    def test_empty_text_raises_loader_error(self) -> None:
        with pytest.raises(LoaderError, match="empty"):
            _parse_text("", "empty_source")

    def test_whitespace_only_raises_loader_error(self) -> None:
        with pytest.raises(LoaderError, match="empty"):
            _parse_text("   \n\t  ", "blank_source")

    def test_invalid_json_raises_loader_error(self) -> None:
        with pytest.raises(LoaderError, match="JSON"):
            _parse_text("{invalid json", "bad.json")

    def test_invalid_yaml_raises_loader_error(self) -> None:
        # A tab character at the start of a YAML value is illegal
        bad_yaml = "key: :\n  - ["
        with pytest.raises(LoaderError, match="YAML"):
            _parse_text(bad_yaml, "bad.yaml")

    def test_non_mapping_raises_loader_error(self) -> None:
        """A YAML list at the top level must raise LoaderError."""
        text = yaml.dump(["item1", "item2"])
        with pytest.raises(LoaderError, match="mapping"):
            _parse_text(text, "list_spec.yaml")

    def test_json_array_raises_loader_error(self) -> None:
        """A JSON array at the top level must raise LoaderError."""
        text = json.dumps([{"openapi": "3.0.0"}])
        with pytest.raises(LoaderError, match="mapping"):
            _parse_text(text, "array_spec.json")

    def test_returns_dict(self) -> None:
        text = yaml.dump({"openapi": "3.0.0", "info": {"title": "T", "version": "1"}})
        result = _parse_text(text, "source")
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# _validate_with_jsonschema
# ---------------------------------------------------------------------------


class TestValidateWithJsonschema:
    """Tests for the JSON Schema-based structural validator."""

    def test_valid_spec_passes(self) -> None:
        """A fully valid spec must not raise."""
        _validate_with_jsonschema(_minimal_spec(), "test")

    def test_missing_openapi_field_raises(self) -> None:
        spec = {"info": {"title": "T", "version": "1"}, "paths": {}}
        with pytest.raises(LoaderError, match="openapi"):
            _validate_with_jsonschema(spec, "test")

    def test_missing_info_field_raises(self) -> None:
        spec = {"openapi": "3.0.0", "paths": {}}
        with pytest.raises(LoaderError, match="info"):
            _validate_with_jsonschema(spec, "test")

    def test_missing_info_title_raises(self) -> None:
        spec = {"openapi": "3.0.0", "info": {"version": "1"}, "paths": {}}
        with pytest.raises(LoaderError):
            _validate_with_jsonschema(spec, "test")

    def test_missing_info_version_raises(self) -> None:
        spec = {"openapi": "3.0.0", "info": {"title": "T"}, "paths": {}}
        with pytest.raises(LoaderError):
            _validate_with_jsonschema(spec, "test")

    def test_openapi_version_2x_raises(self) -> None:
        """An OpenAPI 2.x version string must fail the pattern check."""
        spec = {
            "openapi": "2.0",
            "info": {"title": "T", "version": "1"},
            "paths": {},
        }
        with pytest.raises(LoaderError):
            _validate_with_jsonschema(spec, "test")

    def test_error_message_contains_source(self) -> None:
        spec = {"info": {"title": "T", "version": "1"}, "paths": {}}
        with pytest.raises(LoaderError, match="my_source"):
            _validate_with_jsonschema(spec, "my_source")

    def test_openapi_31_passes(self) -> None:
        """OpenAPI 3.1.x version strings must also pass validation."""
        spec = _minimal_spec(openapi="3.1.0")
        _validate_with_jsonschema(spec, "test")  # must not raise


# ---------------------------------------------------------------------------
# _validate_semantic
# ---------------------------------------------------------------------------


class TestValidateSemantic:
    """Tests for the semantic validator."""

    def test_valid_spec_with_paths(self) -> None:
        _validate_semantic(_minimal_spec(), "test")  # must not raise

    def test_valid_spec_with_components_only(self) -> None:
        spec = {
            "openapi": "3.0.3",
            "info": {"title": "T", "version": "1"},
            "components": {"schemas": {}},
        }
        _validate_semantic(spec, "test")  # must not raise

    def test_no_paths_no_components_raises(self) -> None:
        spec = {
            "openapi": "3.0.3",
            "info": {"title": "T", "version": "1"},
        }
        with pytest.raises(LoaderError, match="paths"):
            _validate_semantic(spec, "test")

    def test_version_2x_raises(self) -> None:
        spec = {
            "openapi": "2.0",
            "info": {"title": "T", "version": "1"},
            "paths": {},
        }
        with pytest.raises(LoaderError, match="3.x"):
            _validate_semantic(spec, "test")

    def test_missing_openapi_key_raises(self) -> None:
        spec = {"info": {"title": "T", "version": "1"}, "paths": {}}
        with pytest.raises(LoaderError, match="3.x"):
            _validate_semantic(spec, "test")


# ---------------------------------------------------------------------------
# load_spec – error paths (integration)
# ---------------------------------------------------------------------------


class TestLoadSpecErrors:
    """Integration-level error path tests for load_spec."""

    def test_missing_file_raises_loader_error(self) -> None:
        with pytest.raises(LoaderError, match="not found"):
            load_spec("/no/such/file/openapi.yaml")

    def test_non_openapi_yaml_raises_loader_error(self, tmp_path: Path) -> None:
        """A generic YAML file that is not an OpenAPI spec must raise."""
        generic_yaml = tmp_path / "generic.yaml"
        generic_yaml.write_text("name: hello\nvalue: world\n", encoding="utf-8")
        with pytest.raises(LoaderError):
            load_spec(str(generic_yaml))

    def test_openapi_2x_file_raises_loader_error(self, tmp_path: Path) -> None:
        """A Swagger 2.0 file must raise LoaderError."""
        swagger2 = {
            "swagger": "2.0",
            "info": {"title": "Old API", "version": "1.0"},
            "paths": {},
        }
        f = tmp_path / "swagger.yaml"
        f.write_text(yaml.dump(swagger2), encoding="utf-8")
        with pytest.raises(LoaderError):
            load_spec(str(f))

    def test_empty_file_raises_loader_error(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.yaml"
        f.write_text("", encoding="utf-8")
        with pytest.raises(LoaderError, match="empty"):
            load_spec(str(f))

    def test_json_spec_loads_correctly(self, tmp_path: Path) -> None:
        spec = _minimal_spec()
        f = tmp_path / "openapi.json"
        f.write_text(json.dumps(spec), encoding="utf-8")
        result = load_spec(str(f))
        assert result["openapi"] == "3.0.3"

    def test_loader_error_is_exception(self) -> None:
        """LoaderError must be a subclass of Exception."""
        assert issubclass(LoaderError, Exception)

    def test_spec_with_servers_field(self, tmp_path: Path) -> None:
        """Specs with a servers list must load without errors."""
        spec = _minimal_spec(servers=[{"url": "https://api.example.com/v1"}])
        f = tmp_path / "spec.yaml"
        f.write_text(yaml.dump(spec), encoding="utf-8")
        result = load_spec(str(f))
        assert result["servers"][0]["url"] == "https://api.example.com/v1"
