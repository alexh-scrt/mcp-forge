# mcp_forge

**Scaffold a fully functional [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server from any OpenAPI 3.x specification – with a single command.**

```bash
mcp-forge generate openapi.yaml --language python --output ./my_server
```

mcp_forge parses your OpenAPI spec, auto-generates typed MCP tool definitions for every endpoint, wires up authentication boilerplate, and writes a ready-to-run server project in either **Python** (using the [`mcp` SDK](https://github.com/modelcontextprotocol/python-sdk)) or **Node.js** (using [`@modelcontextprotocol/sdk`](https://github.com/modelcontextprotocol/typescript-sdk)).

---

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [CLI Reference](#cli-reference)
- [Generated Project Structure](#generated-project-structure)
- [Authentication](#authentication)
- [Examples](#examples)
- [Development](#development)
- [License](#license)

---

## Features

| Feature | Detail |
|---|---|
| **Any OpenAPI 3.x spec** | Accepts local `.yaml`/`.json` files or remote HTTPS URLs |
| **Python & Node.js targets** | Generates idiomatic server code for both runtimes |
| **Auto-typed tool definitions** | MCP `inputSchema` built directly from each OpenAPI operation's parameters and request body |
| **Auth boilerplate** | Bearer token and API key scaffolding from `securitySchemes` |
| **Ready-to-run output** | Dependency files (`requirements.txt` / `package.json`) included – no further setup needed |
| **Fully editable output** | Clean, commented source files you can customise freely |

---

## Requirements

- **Python 3.10+**
- pip

The generated server projects require:
- **Python target**: Python 3.10+, `mcp>=1.0.0`, `httpx>=0.27`
- **Node.js target**: Node.js 18+, `@modelcontextprotocol/sdk^1.0.0`

---

## Installation

### From PyPI (recommended)

```bash
pip install mcp_forge
```

### From source

```bash
git clone https://github.com/your-org/mcp_forge.git
cd mcp_forge
pip install -e .
```

Verify the installation:

```bash
mcp-forge --version
```

---

## Quick Start

### 1. Generate a Python MCP server

```bash
mcp-forge generate openapi.yaml --language python --output ./my_python_server
```

```
✓ MCP server scaffolded successfully!
  Output directory : /home/user/my_python_server
  Language         : python
  Tools generated  : 5
  Auth boilerplate : yes

Files written:
  /home/user/my_python_server/server.py
  /home/user/my_python_server/tools.py
  /home/user/my_python_server/requirements.txt
```

### 2. Run the generated server

```bash
cd my_python_server
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export BEARER_TOKEN=your_api_token
python server.py
```

### 3. Connect with Claude Desktop

Add the following to your Claude Desktop `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "my-api": {
      "command": "python",
      "args": ["/path/to/my_python_server/server.py"],
      "env": {
        "BEARER_TOKEN": "your_api_token"
      }
    }
  }
}
```

---

## CLI Reference

```
Usage: mcp-forge generate [OPTIONS] SPEC

  Generate a fully functional MCP server from an OpenAPI 3.x spec.

  SPEC can be a local file path or a remote URL (http:// or https://).

Options:
  -l, --language [python|node]  Target language for the generated MCP server.
                                [default: python]
  -o, --output TEXT             Output directory for the generated project
                                files.  [default: ./mcp_server]
  -n, --server-name TEXT        Human-readable name for the MCP server.
                                Defaults to the API title from the spec.
  --include-auth / --no-auth    Include authentication boilerplate based on
                                the spec's securitySchemes (Bearer token /
                                API key).  [default: include-auth]
  -v, --verbose                 Print detailed progress information.
  --help                        Show this message and exit.
```

### Options

| Option | Default | Description |
|---|---|---|
| `SPEC` | *(required)* | Local file path or remote URL to the OpenAPI 3.x spec |
| `--language`, `-l` | `python` | Output language: `python` or `node` |
| `--output`, `-o` | `./mcp_server` | Directory to write generated files into |
| `--server-name`, `-n` | spec `info.title` | Display name for the MCP server |
| `--include-auth` / `--no-auth` | `--include-auth` | Include/exclude auth boilerplate |
| `--verbose`, `-v` | off | Print per-operation progress |

---

## Generated Project Structure

### Python

```
my_server/
├── server.py          # MCP server entry point (asyncio + mcp SDK)
├── tools.py           # One async handler function per API operation
└── requirements.txt   # mcp, httpx
```

### Node.js

```
my_server/
├── server.js          # MCP server entry point (@modelcontextprotocol/sdk)
├── tools.js           # One async handler function per API operation
└── package.json       # @modelcontextprotocol/sdk dependency
```

---

## Authentication

mcp_forge reads the `securitySchemes` section of your OpenAPI spec and generates the appropriate boilerplate.

### Bearer Token

For specs with `type: http` / `scheme: bearer` security:

```python
# In generated server.py
BEARER_TOKEN: str = os.environ.get("BEARER_TOKEN", "")
```

Set the environment variable before running:

```bash
export BEARER_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### API Key

For specs with `type: apiKey` security (header-based):

```python
# In generated server.py
API_KEY: str = os.environ.get("API_KEY", "")
```

```bash
export API_KEY=sk-abc123
```

### Disabling Auth

To generate a server without any auth boilerplate:

```bash
mcp-forge generate openapi.yaml --no-auth
```

---

## Examples

### Petstore API (local YAML)

```bash
mcp-forge generate petstore.yaml --language python --output ./petstore_server --verbose
```

### Remote OpenAPI spec

```bash
mcp-forge generate https://api.example.com/openapi.json \
    --language node \
    --output ./my_node_server \
    --server-name "Example API"
```

### No authentication

```bash
mcp-forge generate openapi.yaml --no-auth --output ./public_server
```

### Node.js target

```bash
mcp-forge generate openapi.yaml --language node --output ./node_server
cd node_server
npm install
npm start
```

---

## How It Works

mcp_forge runs the following pipeline:

```
OpenAPI spec (YAML/JSON)
        │
        ▼
  ┌─────────────┐
  │   loader    │  Fetch from file/URL, parse YAML/JSON, validate structure
  └─────────────┘
        │
        ▼
  ┌─────────────┐
  │   parser    │  Convert each operation into a ToolDefinition dataclass
  └─────────────┘
        │
        ▼
  ┌─────────────┐
  │  generator  │  Render Jinja2 templates → write output files
  └─────────────┘
        │
        ▼
  Ready-to-run MCP server project
```

### ToolDefinition

Each OpenAPI operation becomes a `ToolDefinition` capturing:

- **name** – snake_case identifier derived from `operationId` or `{method}_{path}`
- **description** – from `summary` and/or `description`
- **http_method** – `GET`, `POST`, `PUT`, `DELETE`, etc.
- **path** – URL path template, e.g. `/pets/{petId}`
- **parameters** – typed path, query, and header parameters
- **request_body** – schema and field list for request bodies
- **security_schemes** – resolved auth schemes
- **input_schema** – JSON Schema object passed to the MCP `Tool` definition

---

## Development

### Setup

```bash
git clone https://github.com/your-org/mcp_forge.git
cd mcp_forge
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

### Running Tests

```bash
pytest
```

Run with coverage:

```bash
pytest --cov=mcp_forge --cov-report=term-missing
```

### Project Structure

```
mcp_forge/
├── __init__.py          # Version and public API surface
├── cli.py               # Click CLI entry point
├── loader.py            # OpenAPI spec loading and validation
├── models.py            # ToolDefinition and related dataclasses
├── parser.py            # OpenAPI → ToolDefinition conversion
├── generator.py         # Template rendering and file writing
└── templates/
    ├── python/
    │   ├── server.py.j2
    │   ├── tools.py.j2
    │   └── requirements.txt.j2
    └── node/
        ├── server.js.j2
        ├── tools.js.j2
        └── package.json.j2
tests/
├── fixtures/
│   └── petstore.yaml
├── test_loader.py
├── test_models.py
├── test_parser.py
├── test_generator.py
└── test_scaffold.py
```

### Adding a New Template Language

1. Create a new directory under `mcp_forge/templates/<lang>/`
2. Add the three template files: `server.<ext>.j2`, `tools.<ext>.j2`, and a dependency file template
3. Register the plan in `generator._get_template_plan()`
4. Add the language to the CLI `--language` option choices in `cli.py`

---

## Limitations

- **External `$ref`** – References to external URLs or separate files are not resolved; they are passed through unchanged.
- **`oneOf` / `anyOf` / `allOf`** – Composition schemas in request bodies are not expanded into individual fields; the raw schema is passed as-is to the input schema.
- **OAuth2 flows** – OAuth2 is detected and noted in comments but no full flow implementation is generated.
- **OpenAPI 2.x (Swagger)** – Not supported; use a converter such as [swagger2openapi](https://github.com/Mermade/oas-kit) first.

---

## License

MIT License – see [LICENSE](LICENSE) for details.
