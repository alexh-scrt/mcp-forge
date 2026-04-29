# mcp_forge

**Turn any OpenAPI spec into a working MCP server — in one command.**

mcp_forge is a CLI tool that scaffolds a fully functional [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server from any OpenAPI 3.x specification. Point it at a local file or remote URL, choose Python or Node.js, and get a clean, ready-to-run server project with typed tool definitions, request handlers, and authentication boilerplate — all generated automatically.

Stop spending days writing MCP integrations by hand. mcp_forge reduces it to a single command that works immediately with Claude, ChatGPT, and Cursor.

---

## Quick Start

**Install:**

```bash
pip install mcp_forge
```

**Generate a server from a local spec:**

```bash
mcp-forge generate openapi.yaml --language python --output ./my_server
```

**Generate from a remote URL:**

```bash
mcp-forge generate https://api.example.com/openapi.json --language node --output ./my_server
```

**Run your generated server:**

```bash
# Python
cd my_server && pip install -r requirements.txt && python server.py

# Node.js
cd my_server && npm install && npm start
```

That's it. Your MCP server is live and ready to connect.

---

## Features

- **Any OpenAPI 3.x spec as input** — accepts local file paths (YAML or JSON) or remote HTTPS URLs; auto-discovers all endpoints.
- **Python or Node.js output** — generates a complete server using the official [`mcp` SDK](https://github.com/modelcontextprotocol/python-sdk) or [`@modelcontextprotocol/sdk`](https://github.com/modelcontextprotocol/typescript-sdk), your choice.
- **Auto-generated typed tool definitions** — every OpenAPI operation becomes a named MCP tool with a description and a full JSON Schema for its input parameters.
- **Authentication scaffolding** — detects `securitySchemes` in your spec and generates Bearer token / API key boilerplate automatically.
- **Immediately runnable output** — the generated project includes `requirements.txt` or `package.json` so you can install and run without any extra configuration.

---

## Usage Examples

### Generate a Python MCP server from the Stripe API

```bash
mcp-forge generate https://raw.githubusercontent.com/stripe/openapi/master/openapi/spec3.yaml \
  --language python \
  --output ./stripe_mcp_server \
  --name "Stripe API Server"
```

### Generate a Node.js MCP server from a local spec, skipping auth scaffolding

```bash
mcp-forge generate ./specs/github.yaml \
  --language node \
  --output ./github_mcp_server \
  --name "GitHub API Server" \
  --no-auth
```

### Check the version

```bash
mcp-forge --version
```

### Generated Python output (excerpt)

```python
# my_server/tools.py  (auto-generated, fully editable)

async def list_pets(arguments: dict, headers: dict, base_url: str) -> dict:
    """List all pets."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{base_url}/pets",
            headers=headers,
            params={k: arguments[k] for k in ["limit"] if k in arguments},
        )
        response.raise_for_status()
        return response.json()
```

### Generated Node.js output (excerpt)

```javascript
// my_server/tools.js  (auto-generated, fully editable)

async function listPets({ arguments: args, headers, baseUrl }) {
  const url = new URL(`${baseUrl}/pets`);
  if (args.limit !== undefined) url.searchParams.set('limit', args.limit);
  const res = await fetch(url, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
```

---

## Project Structure

```
mcp_forge/
├── __init__.py                      # Package init, version string
├── cli.py                           # Click CLI — the 'generate' command
├── loader.py                        # Load & validate OpenAPI specs (file or URL)
├── parser.py                        # Parse spec into ToolDefinition dataclasses
├── generator.py                     # Render Jinja2 templates, write output files
├── models.py                        # ToolDefinition, ToolParameter, SecurityScheme
└── templates/
    ├── python/
    │   ├── server.py.j2             # Python MCP server entry point
    │   ├── tools.py.j2              # Python tool handler functions
    │   └── requirements.txt.j2     # Python dependencies
    └── node/
        ├── server.js.j2             # Node.js MCP server entry point
        ├── tools.js.j2              # Node.js tool handler functions
        └── package.json.j2         # Node.js package manifest
tests/
├── test_loader.py
├── test_parser.py
├── test_generator.py
├── test_models.py
├── test_scaffold.py
└── fixtures/
    └── petstore.yaml               # Minimal Petstore spec for testing
pyproject.toml
README.md
```

---

## Configuration

All configuration is passed via CLI flags on the `generate` command:

| Flag | Default | Description |
|---|---|---|
| `SPEC` (positional) | — | Path or HTTPS URL to an OpenAPI 3.x spec (**required**) |
| `--language`, `-l` | `python` | Target language: `python` or `node` |
| `--output`, `-o` | `./mcp_server` | Directory to write the generated project into |
| `--name`, `-n` | Derived from spec `info.title` | Display name for the generated server |
| `--auth / --no-auth` | `--auth` | Include or skip authentication boilerplate |

**Environment variables in generated servers:**

The generated server reads credentials from environment variables at runtime:

```bash
# Bearer token auth
export API_TOKEN="your_token_here"
python server.py

# API key auth
export API_KEY="your_key_here"
node server.js
```

---

## Requirements

- Python 3.10+
- For generated **Python** servers: `mcp>=1.0.0`, `httpx>=0.27`
- For generated **Node.js** servers: Node.js 18+, `@modelcontextprotocol/sdk^1.0.0`

---

## License

MIT — see [LICENSE](LICENSE) for details.

---

*Built with [Jitter](https://github.com/jitter-ai) - an AI agent that ships code daily.*
