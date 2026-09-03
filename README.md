# wiki-mcp

A fast, read-only [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server for [Karpathy-style LLM Markdown wikis](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

Exposes **only 3 read-only tools** so AI agents can understand and query your knowledge base without any risk of modifying or deleting files:
1. **`read_orientation()`**: Reads `SCHEMA.md`, `index.md`, and the last 30 lines of `log.md` in a single roundtrip.
2. **`search_wiki(query, tag=None)`**: Fast full-text and taxonomy-tag search across curated wiki directories (`concepts/`, `entities/`, `comparisons/`, `queries/`).
3. **`get_page(slug_or_path)`**: Safely reads any wiki page, cleanly parsing frontmatter YAML and markdown body.

---

## Requirements

* Python >= 3.11
* [uv](https://docs.astral.sh/uv/) (recommended) or `pip`

---

## Quickstart

Run directly against your wiki using `uv`:

```bash
uv run --directory /Users/paolo/Projects/wiki-mcp wiki-mcp --wiki-dir /Users/paolo/Projects/dev-wiki
```

Or install in a virtual environment:
```bash
cd /Users/paolo/Projects/wiki-mcp
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
pytest
```

---

## MCP Client Configuration

### 1. Antigravity IDE
Add to `.agents/mcp_config.json` in your workspace or `~/.gemini/config/mcp_config.json`:

```json
{
  "mcpServers": {
    "dev-wiki": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/Users/paolo/Projects/wiki-mcp",
        "wiki-mcp",
        "--wiki-dir",
        "/Users/paolo/Projects/dev-wiki"
      ]
    }
  }
}
```

### 2. Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "dev-wiki": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/Users/paolo/Projects/wiki-mcp",
        "wiki-mcp",
        "--wiki-dir",
        "/Users/paolo/Projects/dev-wiki"
      ]
    }
  }
}
```

### 3. Cursor (`.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "dev-wiki": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/Users/paolo/Projects/wiki-mcp",
        "wiki-mcp",
        "--wiki-dir",
        "/Users/paolo/Projects/dev-wiki"
      ]
    }
  }
}
```

---

## Security & Architecture

* **Purely Read-Only:** Zero file mutation or deletion tools are exposed. Deletions and edits remain strictly under human / Git control.
* **Path Traversal Protection:** All file reads are strictly constrained to the specified `--wiki-dir`.
* **Decoupled Architecture:** Your markdown notes repository contains zero code or runtime dependencies.
