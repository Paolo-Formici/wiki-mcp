# Architecture & Feature Backlog

## Backlog Items

### 1. Branch & Pull Request Automation for Agent Writes
* **Status**: Backlog — Revisit when an agent actually needs to write to the wiki
* **Context**:
  The current production architecture operates as a **Read-Only MCP Server** to guarantee zero merge conflicts and preserve the integrity of the `main` branch. All human updates flow via standard Git commits/PRs or Obsidian, and the central MCP server pulls updates automatically via webhooks.
* **Proposed Enhancement**:
  Allow AI agents to propose changes to the wiki without compromising `main` branch stability.
  We want stability and control over the wiki but at the same time people, through ai or without need to contribute to follow the principles of a wiki:
  "Convergence Over Locking" (Soft Security):
  Classical wikis don't lock pages while people edit. Instead, they rely on revision   history and the assumption that the community will iteratively converge on the   correct content.
* **Architecture Design**:
  1. **Write Tool**: Expose `propose_page_update(path, content, summary)` or `propose_raw_ingest(url, content)`.
  2. **Branching**: Instead of committing to the active working tree or `main`, the server (or a worker utilizing the GitHub/GitLab REST API) creates a dedicated branch:
     `bot/update-<timestamp>-<slug>`
  3. **Commit & Attribution**:
     * Commit the new/updated Markdown page.
     * Attribute the commit to the requesting developer (extracted from request headers e.g. `X-Dev-Email`) or a designated Wiki Bot.
  4. **Pull Request Generation**:
     * Open a Pull Request against `main`.
     * Include the generated summary, changed files, and diff in the PR body.
  5. **Review & Merge**:
     * Human team members / admin review the PR.
     * When merged to `main`, the existing GitHub Webhook triggers the central MCP server's `git pull`, seamlessly incorporating the new knowledge into the read pool for all developers.
* **Key Benefits**:
  * Adheres to the Wiki Principle of **Soft Security & Observability** (all edits are visible, reviewable, and reversible).
  * Completely sidesteps headless Git merge conflict traps.
  * Allows agents to assist in drafting knowledge while keeping humans firmly in the loop.
* **YAGNI Note**: Not building this until there's a real agent trying to write. The read-only loop works today.

### 2. Automated AI Ingestion from `raw/repos/` into Curated Layers (`entities/`, `concepts/`)
* **Status**: Backlog / Explicitly Deferred (Manual Curation for Now)
* **Context**:
  `wiki-mcp` automatically syncs 1:1 documentation and contracts from company repositories into `raw/repos/<repo-name>/` via webhook push.
* **Proposed Enhancement**:
  When new or modified raw documentation lands in `raw/repos/<repo-name>/`, trigger an AI agent pipeline to:
  1. Detect whether the repository is a newly ingested service or an update to an existing one.
  2. Propose or update entity pages under `entities/<repo-name>.md` with high-level architecture, ownership, dependencies, and `[[wikilinks]]`.
  3. Synthesize relevant design patterns or cross-service interactions into `concepts/`.
* **Decision (YAGNI & Human-in-the-Loop)**:
  Deferred. Ingestion and synthesis into curated pages will remain a manual, human-directed activity (or prompted locally on-demand via LLM) to avoid noise, hallucinated pages, and unnecessary repository churn.

### 3. Items Explicitly Deferred (YAGNI)
* **SQLite FTS5 search** — Wiki is 106 pages. Linear substring scan in `search_wiki()` is sub-millisecond. Revisit at 500+ pages.
* **CI lint pipeline** — No PRs flowing, no multi-contributor workflow yet. Lint is an agent skill invoked manually.
* **Backlinks / graph navigation tool** — Would be nice, not blocking anything. Agents can grep for `[[page-name]]` today.

