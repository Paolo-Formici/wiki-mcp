# Next: Let Git Be Git

## The Problem

The Karpathy LLM-Wiki pattern was designed for a plain directory of markdown files
with no version control. It invented its own versioning layer:

- `log.md` — append-only changelog of every action (duplicates `git log`)
- `sha256` in raw/ frontmatter — content hashing to detect drift (duplicates `git diff`)
- `updated:` date bumping — manual staleness tracking (duplicates `git log --follow`)

Now that dev-wiki is git-backed and served via dev-mcp with webhook-triggered
`git pull`, all three are redundant work that adds merge-conflict risk for zero value.

## What to Change

### 1. Drop `log.md` from the workflow
- **SCHEMA.md**: Remove "Every action must be appended to `log.md`" convention
- **SKILL.md**: Remove log.md orientation step, remove log.md append from ingest/query/lint flows
- **dev-mcp `read_orientation()`**: Replace `log.md` tail with `git log -n 10 --oneline --stat`
- **dev-wiki**: Keep existing log.md as-is (it's historical record), just stop appending to it
- Git commit messages become the log. They already are — we were writing them twice.

### 2. Drop `sha256` from raw/ frontmatter
- **SCHEMA.md**: Remove `sha256:` from raw frontmatter spec
- **SKILL.md**: Remove sha256 compute/compare from ingest and lint flows
- Re-ingest detection: `git log --oneline raw/articles/<file>` shows if/when it was touched
- Source drift detection: re-fetch URL, diff against `git show HEAD:raw/articles/<file>`
- Don't retroactively strip sha256 from existing files — YAGNI, causes pointless churn

### 3. Add `get_recent_changes()` tool to dev-mcp
- Replaces `log.md` tail reading for agent orientation
- Wraps `git log` / `git diff --stat` — what actually changed, by whom, when
- Simple. Uses what's already there.

## What NOT to Do (YAGNI)

- SQLite FTS5 search — 106 pages, linear scan is sub-millisecond
- CI linting pipeline — no PRs flowing yet, no contributors to lint for
- Backlinks/graph tool — not blocking anything today
- Agent write/PR loop — already in backlog, revisit when an agent actually needs to write

## Sequence

1. Update SCHEMA.md in dev-wiki (remove log.md convention, remove sha256 spec)
2. Update SKILL.md in dev-wiki (remove log.md and sha256 from all flows)
3. Add `get_recent_changes()` tool to dev-mcp
4. Update `read_orientation()` to use git log instead of log.md
5. Test locally via stdio mode