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
| `WIKI_GIT_BRANCH` | Git branch to push synced raw docs to | `main` |
| `AUTH_TOKEN` | Bearer token required for `/mcp` endpoints | `None` (open) |
| `WIKI_WEBHOOK_SECRET` | Secret for verifying wiki repository webhooks | `None` (open) |
| `REPO_WEBHOOK_SECRET` | Secret for verifying external team repo webhooks | `None` (open, YAGNI) |
| `GITHUB_TOKEN` | GitHub API token for fetching files 1:1 from repos | `None` (unauthenticated) |
| `ALLOWED_REPOS` | Comma-separated allowlist of repos to sync | `None` (all incoming) |
| `SYNC_CRON` | Standard 5-field cron expression for periodic git pull (e.g. `*/5 * * * *`) | `None` (webhook-only) |
| `LOG_LEVEL` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |

---

### Remote Git Sync Modes
`wiki-mcp` remote mode supports three operational synchronization models:
1. **Webhook-only (Default):** Set `WIKI_WEBHOOK_SECRET`. When commits are pushed to the wiki repository, GitHub/GitLab hits `POST /webhook` to trigger an immediate `git pull --ff-only`.
2. **Cron-only (Zero-Ingress / Private Networks):** Set `SYNC_CRON="*/5 * * * *"`. The server periodically runs `git pull --ff-only` in the background. Ideal for air-gapped or private networks/VPCs where opening inbound webhook ingress is not possible or desired.
3. **Hybrid (GitOps Best Practice):** Configure both `WIKI_WEBHOOK_SECRET` and `SYNC_CRON`. Pushes trigger instant zero-latency sync via webhook, while the cron scheduler acts as a background reconciliation loop ensuring eventual consistency. An internal `asyncio.Lock` guarantees that webhook and cron runs never collide.

---

## Remote Endpoints

* **`POST /mcp`**: The core MCP Streamable HTTP endpoint. If `AUTH_TOKEN` is configured, requests must supply `Authorization: Bearer <AUTH_TOKEN>`.
* **`GET /health`**: Public liveness and readiness probe for load balancers. Returns health and detailed sync state:
  ```json
  {
    "status": "healthy",
    "wiki": "/data/wiki",
    "commit": "a1b2c3d",
    "sync": {
      "mode": "hybrid",
      "cron_expression": "*/5 * * * *",
      "cron_enabled": true,
      "last_sync_at": "2026-09-08T12:05:00.123456+00:00",
      "last_sync_trigger": "cron",
      "last_sync_status": "synced",
      "last_sync_commit": "a1b2c3d",
      "last_sync_error": null
    }
  }
  ```
* **`POST /webhook`**: Inbound webhook for the wiki's own repo (GitHub `X-Hub-Signature-256` / GitLab `X-Gitlab-Token`). Automatically triggers `git pull --ff-only` on the local mirror.
* **`POST /webhook/repo-sync`**: Inbound webhook for external team repositories. Selectively filters for documentation (`README*`, `docs/**`, ADRs, OpenAPI contracts), fetches them verbatim 1:1 via GitHub REST API, saves them into `raw/repos/<repo-name>/...`, commits, and pushes directly to the wiki's remote Git repository. Secret verification is strictly optional (YAGNI).



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

## Architecture Overview

```mermaid
flowchart TB
    subgraph Clients["Clients & Developers"]
        IDE1["Local IDE (stdio)<br/>Cursor / Antigravity / Claude"]
        IDE2["Team IDEs (HTTP MCP 2.x)<br/>Header: Bearer Token"]
        HumanDev["Human Curators<br/>Obsidian / VS Code"]
    end

    subgraph Server["wiki-mcp Server"]
        AuthMiddleware["TokenAuthMiddleware<br/>/mcp security"]
        FastMCPEngine["FastMCP Read-Only Engine<br/>read_orientation, search_wiki, get_page"]
        
        subgraph SyncEngine["Git Sync & Ingestion Engine"]
            WikiPull["Self-Mirror Sync<br/>POST /webhook<br/>(git pull --ff-only)"]
            DocSync["Selective Doc Ingestion<br/>POST /webhook/repo-sync<br/>(1:1 GitHub API Fetch & Push)"]
        end
    end

    subgraph Storage["dev-wiki Filesystem Mirror"]
        Curated["Curated Layer (Silver/Gold)<br/>concepts/, entities/, comparisons/"]
        Raw["Raw Layer (Bronze)<br/>raw/articles/, raw/repos/<repo>/..."]
    end

    subgraph Remotes["Remote Git Repositories"]
        WikiRemote["Central dev-wiki Repo<br/>(GitHub / GitLab)"]
        TeamRepos["External Team Repos<br/>(billing-service, auth-service, ...)"]
    end

    %% Client flows
    IDE1 -->|"Direct Local stdio"| FastMCPEngine
    IDE2 -->|"POST /mcp"| AuthMiddleware
    AuthMiddleware --> FastMCPEngine
    FastMCPEngine -->|"Read-only queries"| Storage
    HumanDev -->|"git commit & push"| WikiRemote

    %% Webhook & Sync flows
    WikiRemote -->|"Push Event Webhook"| WikiPull
    WikiPull -->|"Fast-forward pull"| Storage
    
    TeamRepos -->|"Push Webhook (Docs/ADR)"| DocSync
    DocSync -->|"Write 1:1 verbatim"| Raw
    DocSync -->|"git commit & push origin main"| WikiRemote
```

---

## How Selective Doc Sync Works (`/webhook/repo-sync`)

```mermaid
sequenceDiagram
    autonumber
    participant TeamRepo as External Team Repo
    participant MCP as wiki-mcp Server
    participant GH as GitHub REST API
    participant Disk as Local Wiki Disk (raw/repos/)
    participant Remote as dev-wiki Remote (main)

    TeamRepo->>MCP: POST /webhook/repo-sync (push payload)
    Note over MCP: Optional HMAC signature check (YAGNI)
    
    alt Commits contain only source code (e.g. src/**/*.ts)
        MCP-->>TeamRepo: 200 OK {"status": "skipped", "message": "No doc files modified"}
    else Commits modify README, docs/**, ADRs, or API contracts
        Note over MCP: Filter doc files (README*, docs/**, *.md, openapi.*)
        loop For each modified doc file
            MCP->>GH: GET /repos/{owner}/{repo}/contents/{path}?ref={sha}
            GH-->>MCP: Raw 1:1 file bytes
            MCP->>Disk: Write verbatim to raw/repos/{repo}/{path}
        end
        
        MCP->>Disk: git add raw/repos/{repo}/
        MCP->>Disk: git commit -m "chore(raw): sync {repo} docs from {sha}"
        
        loop Push with Rebase Retry (up to 3x)
            MCP->>Remote: git push origin main
            alt Push rejected (remote progressed)
                MCP->>Remote: git pull --rebase origin main
            else Push accepted
                Note over MCP: Push successful
            end
        end
        
        MCP-->>TeamRepo: 200 OK {"status": "synced", "files": [...]}
    end
```

---

## Wiki Convergence Flow

```mermaid
sequenceDiagram
    autonumber
    participant Dev as Developer / Curator
    participant GH as dev-wiki Remote (GitHub)
    participant MCP as Central wiki-mcp Daemon
    participant Agent as Developer AI Agent (Cursor / Antigravity)

    Dev->>GH: git push origin main (edits entities/ or concepts/)
    GH->>MCP: POST /webhook (HMAC verified)
    MCP->>MCP: git pull --ff-only
    Note over MCP: Local wiki cache updated in milliseconds
    
    Agent->>MCP: POST /mcp (read_orientation / search_wiki / get_page)
    MCP-->>Agent: Returns fresh, synchronized knowledge
```

---

## Principles & Architecture

* **12-Factor XI (Logs):** Treats logs as unbuffered structured JSON event streams to `stdout`.
* **12-Factor III (Config):** Configuration driven strictly by environment variables.
* **Gall's Law & YAGNI:** Starts from a simple, reliable core (shallow Git clone + FastMCP + webhook) without unnecessary database or caching bloat.
* **Wiki Principles (Ward Cunningham):** Convergence over locking, soft security via read-only access, and transparent observability via Git commit history and `log.md`.

