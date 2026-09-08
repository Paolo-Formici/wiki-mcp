# Architecture & Plan History: 1:1 Selective Doc Sync into `raw/repos/`

* **Date:** 2026-09-07
* **Status:** Approved & In Progress

---

## 1. Context & Motivation
To enable `dev-wiki` to accumulate knowledge from multiple company repositories without suffering from Git repository bloat, merge conflicts, or high noise for LLMs, we implement **Selective Documentation Ingestion**:
- Only documentation and contract files (`README.md`, `docs/**`, ADRs, OpenAPI specs) are mirrored into `raw/repos/<repo-name>/`.
- The mirrored files are **1:1 verbatim replicas** of the source repository at the triggering commit.
- Ingestion into the curated layers (`entities/`, `concepts/`) is done on-demand / manually (automated AI synthesis is deferred in backlog).
- The remote `wiki-mcp` server commits and pushes these changes directly to the `dev-wiki` remote.
- **Local developer workflow is 100% preserved**: local editing in Obsidian / IDE continues with zero merge conflicts because `raw/repos/` is completely orthogonal to curated folders.

---

## 2. Core Decisions & Wiki Principles Alignment
* **Selective Ingestion (Signal vs Noise):** Code trees are filtered out; only high-density documentation and architecture decision records are preserved.
* **1:1 Raw Fidelity (Bronze Layer):** The raw layer remains pure, immutable relative to the upstream source commit, with no premature AI transformation.
* **YAGNI & Simplicity:**
  * No mandatory Org Webhook: works natively with single repo webhooks or selected repos.
  * HMAC / Webhook Secret is optional (no signature check enforced if secret is not configured).
  * Push retry with rebase handles transient contention smoothly.

---

## 3. Architecture Design

```
+-------------------------------------------------------------+
| Selected Team Repository (e.g. billing-service)             |
| Push to 'main' modifying README.md or docs/architecture.md  |
+-------------------------------------------------------------+
                               |
                               | GitHub Webhook (per-repo or org)
                               v
+-------------------------------------------------------------+
| wiki-mcp (Remote Mode)                                      |
| Endpoint: POST /webhook/repo-sync                           |
| 1. Optional Secret check (if secret configured, else open)  |
| 2. Filter payload commits for doc paths                     |
| 3. Fetch modified files 1:1 via GitHub REST API             |
| 4. Write verbatim into <wiki_dir>/raw/repos/<repo_name>/... |
| 5. Git commit: "chore(raw): sync <repo> docs at <sha>"      |
| 6. Git push origin main (with rebase retry on contention)   |
+-------------------------------------------------------------+
                               |
                               | Git Push
                               v
+-------------------------------------------------------------+
| Central dev-wiki GitHub Remote                              |
+-------------------------------------------------------------+
                               |
                               | git pull
                               v
+-------------------------------------------------------------+
| Paolo's Local Environment (Obsidian / VS Code / stdio MCP)  |
| - Pulls new raw docs without conflicts                      |
| - Manually synthesizes entities/concepts when needed        |
+-------------------------------------------------------------+
```

---

## 4. Planned Implementation Steps

1. **`src/wiki_mcp/repo_sync.py`**:
   - `is_doc_file(path)`: match against `README*`, `docs/**`, `doc/**`, `*.adr.md`, `openapi.*`, etc.
   - `extract_modified_doc_files(payload)`: parse push webhook payload.
   - `fetch_github_file_async(repo_full_name, path, ref, token)`: fetch file bytes from GitHub API.
   - `sync_repo_docs_to_disk(wiki_dir, repo_name, files_to_write, files_to_delete)`.
2. **`src/wiki_mcp/git_sync.py`**:
   - `commit_and_push_async(wiki_dir, target_subpath, message, branch)` with rebase retry.
3. **`src/wiki_mcp/remote.py`**:
   - Expose `POST /webhook/repo-sync` endpoint with optional HMAC and optional repo filter.
4. **`src/wiki_mcp/cli.py`**:
   - Expose CLI and env configs (`GITHUB_TOKEN`, `REPO_WEBHOOK_SECRET`, `ALLOWED_REPOS`).
5. **Tests & Verification**:
   - Add unit and integration tests in `tests/test_repo_sync.py`.
