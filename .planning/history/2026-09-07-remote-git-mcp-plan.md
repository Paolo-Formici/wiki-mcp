# Architecture & Plan History: Remote Git-Backed Wiki MCP Server

* **Date:** 2026-09-07
* **Status:** Approved & Implemented

---

## 1. Context & Motivation
Originally, `wiki-mcp` was designed as a local read-only MCP tool operating over `stdio` on a single developer machine.
To support engineering teams, the architecture was evolved into a **centralized, remote MCP service** over **Streamable HTTP** (MCP 2.x standard) backed by a remote Git repository (e.g., GitHub or GitLab) as the single source of truth.

---

## 2. Core Decisions & Wiki Principles Alignment

### Alignment with Software Engineering Principles (Curated in Dev-Wiki)
* **[12-Factor XI: Logs](file:///Users/paolo/Projects/dev-wiki/concepts/12factor-logs.md):** The application never manages log files or rotation. All events are emitted unbuffered to `stdout` as structured streams for the platform (Docker/Kubernetes/cloud) to capture and aggregate.
* **[12-Factor III: Config](file:///Users/paolo/Projects/dev-wiki/concepts/12factor-config.md):** Strict configuration via environment variables (`WIKI_GIT_URL`, `WIKI_PATH`, `PORT`, `AUTH_TOKEN`, `WIKI_WEBHOOK_SECRET`).
* **[12-Factor IX: Disposability](file:///Users/paolo/Projects/dev-wiki/concepts/12factor-disposability.md):** Fast startup (shallow clone `--depth 50` or fast `pull --ff-only`) and graceful shutdown.
* **[YAGNI](file:///Users/paolo/Projects/dev-wiki/concepts/yagni.md) & [Gall's Law](file:///Users/paolo/Projects/dev-wiki/concepts/galls-law.md):** Avoid premature complexity (no heavy external databases or sync clusters). Evolved from the working local system: Git mirror + FastMCP + Webhook.
* **Ward Cunningham's Wiki Principles:**
  * *Simple / Mundane:* Git + Markdown + FastMCP.
  * *Convergence over Locking:* Central read-only MCP serving `main`. Devs commit/PR independently. As commits land on `main`, the webhook triggers `git pull` and the wiki converges instantly.
  * *Observable:* Full commit history on GitHub + `log.md` entries remain the transparent audit trail.

---

## 3. Component Architecture

```
 [ Developer IDEs ] (Cursor / Antigravity / Claude Desktop)
        │
        │  Streamable HTTP (MCP 2.x)
        │  Header: "Authorization: Bearer <AUTH_TOKEN>"
        ▼
 ┌────────────────────────────────────────────────────────────┐
 │  Remote Server (Docker / VM)                               │
 │                                                            │
 │  ┌──────────────────────────────────────────────────────┐  │
 │  │  FastMCP / MCPServer Process                         │  │
 │  │                                                      │  │
 │  │  • /mcp endpoint       -> Streamable HTTP (3 Tools)  │  │
 │  │  • /webhook endpoint   -> GitHub/GitLab Webhook      │  │
 │  │  • /health endpoint    -> Healthcheck probe          │  │
 │  └───────────────────────────────┬──────────────────────┘  │
 │                                  │ (Async git pull on push)│
 │                                  ▼                         │
 │  Local Mirror: /data/wiki (Sub-millisecond disk reads)     │
 └──────────────────────────────────┬─────────────────────────┘
                                    │
                                    │ git clone / git pull
                                    ▼
                      ┌──────────────────────────┐
                      │  GitHub / GitLab Repo    │
                      │  (Source of Truth)       │
                      └─────────────▲────────────┘
                                    │
                                    │ git push / PR merge
                      [ Devs / Obsidian / CI ]
```

### Authentication Details
* **Clients (`/mcp`):** Protected by `AUTH_TOKEN`. If set, requests must provide `Authorization: Bearer <AUTH_TOKEN>`. Validated via constant-time comparison (`hmac.compare_digest`).
* **Webhooks (`/webhook`):** Protected by `WIKI_WEBHOOK_SECRET` via HMAC SHA-256 (`X-Hub-Signature-256`) or GitLab token.
* **Health Check (`/health`):** Unauthenticated for load balancer probes.

### Backlog Reference
* Agent-driven write operations via automated branch creation and Pull Requests are cataloged for future evaluation in [.planning/backlog.md](file:///Users/paolo/Projects/dev-wiki/.planning/backlog.md).
