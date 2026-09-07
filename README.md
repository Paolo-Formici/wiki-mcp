# wiki-mcp

A fast, read-only [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server for [Karpathy-style LLM Markdown wikis](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

Supports both **Local Mode** (`stdio`) and **Remote Mode** (**Streamable HTTP**, MCP 2.x standard) backed by a Git repository with automatic webhook synchronization.

---

## The 3 Read-Only Tools

1. **`read_orientation()`**: Reads `SCHEMA.md`, `index.md`, and the last 30 lines of `log.md` in a single roundtrip.
2. **`search_wiki(query, tag=None)`**: Fast full-text and taxonomy-tag search across curated wiki directories (`concepts/`, `entities/`, `comparisons/`, `queries/`).
3. **`get_page(slug_or_path)`**: Safely reads any wiki page, cleanly parsing frontmatter YAML and markdown body.

Zero file mutation or deletion tools are exposed, guaranteeing your wiki's integrity.

---

## Running in Local Mode (stdio)

Run directly against your local wiki using `uv`:

```bash
uv run --directory /Users/paolo/Projects/wiki-mcp wiki-mcp --wiki-dir /path/to/wiki
```

### Local Client Config (`mcp_config.json`):
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
        "/path/to/wiki"
      ]
    }
  }
}
```

---

## Running in Remote Mode (Streamable HTTP)

In Remote Mode, `wiki-mcp` runs as a centralized daemon on a server or Docker container. It clones/pulls the wiki Git repo on startup and listens for incoming IDE connections and GitHub/GitLab webhooks.

### CLI Launch
```bash
uv run --directory /Users/paolo/Projects/wiki-mcp wiki-mcp   --remote   --host 0.0.0.0   --port 8000   --wiki-dir /data/wiki   --git-url "https://github.com/your-org/dev-wiki.git"   --auth-token "team-secret-token"   --webhook-secret "webhook-hmac-secret"
```

### Environment Variables
| Variable | Description | Default |
| :--- | :--- | :--- |
| `REMOTE_MODE` | Set to `true` or `1` for HTTP mode | `false` |
| `HOST` | Bind address | `0.0.0.0` |
| `PORT` | HTTP port | `8000` |
| `WIKI_PATH` | Local filesystem path to cache/clone wiki | Current directory |
| `WIKI_GIT_URL` | Git remote URL to clone if path is empty | `None` |
| `AUTH_TOKEN` | Bearer token required for `/mcp` endpoints | `None` (open) |
| `WIKI_WEBHOOK_SECRET` | Secret for verifying GitHub/GitLab webhooks | `None` (open) |
| `LOG_LEVEL` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |

---

## Remote Endpoints

* **`POST /mcp`**: The core MCP Streamable HTTP endpoint. If `AUTH_TOKEN` is configured, requests must supply `Authorization: Bearer <AUTH_TOKEN>`.
* **`GET /health`**: Public liveness and readiness probe for load balancers. Returns `{"status": "healthy", "commit": "..."}`.
* **`POST /webhook`**: Inbound webhook for GitHub (`X-Hub-Signature-256`) and GitLab (`X-Gitlab-Token`). Automatically triggers `git pull --ff-only` on the local mirror.

---

## Docker Deployment

### Docker Compose
```bash
docker compose up -d
```

### Docker Run
```bash
docker run -d \
  -p 8000:8000 \
  -v wiki-data:/data/wiki \
  -e WIKI_GIT_URL="https://github.com/your-org/dev-wiki.git" \
  -e AUTH_TOKEN="team-secret-token" \
  -e WIKI_WEBHOOK_SECRET="webhook-hmac-secret" \
  wiki-mcp:latest
```

---

## Developer Client Setup (Remote)

Developers on your team point their IDE (Antigravity IDE, Cursor, Claude Desktop) to your centralized instance:

```json
{
  "mcpServers": {
    "team-wiki": {
      "url": "https://wiki.internal.company.com/mcp",
      "headers": {
        "Authorization": "Bearer team-secret-token"
      }
    }
  }
}
```

---

## Principles & Architecture

* **12-Factor XI (Logs):** Treats logs as unbuffered structured JSON event streams to `stdout`.
* **12-Factor III (Config):** Configuration driven strictly by environment variables.
* **Gall's Law & YAGNI:** Starts from a simple, reliable core (shallow Git clone + FastMCP + webhook) without unnecessary database or caching bloat.
* **Wiki Principles (Ward Cunningham):** Convergence over locking, soft security via read-only access, and transparent observability via Git commit history and `log.md`.
