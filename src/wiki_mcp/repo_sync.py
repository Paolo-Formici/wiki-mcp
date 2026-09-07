import fnmatch
import os
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import httpx
from wiki_mcp.logger import get_logger, log_event

logger = get_logger("wiki_mcp.repo_sync")

DOC_DIR_PREFIXES = ("docs/", "doc/", "documentation/", "adr/")
IGNORED_SUBSTRINGS = ("node_modules/", ".git/", "dist/", "build/", "__pycache__/", ".pytest_cache/")


def is_doc_file(filepath: str, patterns: Optional[List[str]] = None) -> bool:
    """
    Determines if a file path qualifies as a documentation or interface contract file.
    Filters out noise like source code, node_modules, build artifacts.
    """
    normalized = filepath.replace("\\", "/").strip("/")
    lower = normalized.lower()

    if any(ignored in lower for ignored in IGNORED_SUBSTRINGS):
        return False

    if patterns:
        return any(fnmatch.fnmatch(lower, p.lower()) or fnmatch.fnmatch(os.path.basename(lower), p.lower()) for p in patterns)

    base = os.path.basename(lower)
    return (
        lower.startswith(DOC_DIR_PREFIXES)
        or base.startswith("readme")
        or base.endswith(".md")
        or base.startswith(("openapi.", "swagger.", "schema.graphql"))
    )


    return False


def extract_modified_doc_files(
    payload: dict,
    allowed_repos: Optional[List[str]] = None,
) -> Tuple[Optional[str], Optional[str], Optional[str], Set[str], Set[str]]:
    """
    Extracts repo name, full name, commit SHA, and modified/deleted doc file sets
    from a GitHub push webhook payload.

    Returns:
        (repo_name, repo_full_name, commit_sha, files_to_sync, files_to_delete)
    """
    repository = payload.get("repository", {})
    repo_name = repository.get("name")
    repo_full_name = repository.get("full_name") or repo_name
    commit_sha = payload.get("after") or (payload.get("head_commit") or {}).get("id")

    if not repo_name or not commit_sha:
        return None, None, None, set(), set()

    # Optional repository filtering
    if allowed_repos:
        allowed_set = {r.strip().lower() for r in allowed_repos if r.strip()}
        if repo_name.lower() not in allowed_set and repo_full_name.lower() not in allowed_set:
            log_event(
                logger, 20, "repo_sync_skipped",
                f"Repository {repo_name} is not in allowed_repos list",
                repo=repo_name
            )
            return None, None, None, set(), set()

    files_to_sync: Set[str] = set()
    files_to_delete: Set[str] = set()

    commits = payload.get("commits", [])
    if not commits and "head_commit" in payload:
        commits = [payload["head_commit"]]

    for commit in commits:
        for path in commit.get("added", []) + commit.get("modified", []):
            if is_doc_file(path):
                files_to_sync.add(path)
                files_to_delete.discard(path)

        for path in commit.get("removed", []):
            if is_doc_file(path):
                files_to_delete.add(path)
                files_to_sync.discard(path)

    return repo_name, repo_full_name, commit_sha, files_to_sync, files_to_delete


async def fetch_github_file_async(
    repo_full_name: str,
    file_path: str,
    ref: str,
    client: httpx.AsyncClient,
    token: Optional[str] = None,
) -> Optional[bytes]:
    """
    Fetches raw file content verbatim from GitHub REST API.
    Uses 'application/vnd.github.raw+json' to get untransformed raw bytes.
    """
    url = f"https://api.github.com/repos/{repo_full_name}/contents/{file_path}"
    headers = {
        "Accept": "application/vnd.github.raw+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "wiki-mcp-repo-sync",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        resp = await client.get(url, params={"ref": ref}, headers=headers)
        if resp.status_code == 200:
            return resp.content
        log_event(
            logger, 30, "github_fetch_warning",
            f"Failed to fetch {file_path} from {repo_full_name}: HTTP {resp.status_code}",
            status_code=resp.status_code, path=file_path,
        )
    except Exception as e:
        log_event(
            logger, 40, "github_fetch_error",
            f"Exception fetching {file_path} from {repo_full_name}: {str(e)}",
            path=file_path, error=str(e),
        )
    return None


def sync_repo_docs_to_disk(
    wiki_dir: Path,
    repo_name: str,
    files_content: Dict[str, bytes],
    files_to_delete: Set[str],
) -> List[Path]:
    """
    Writes updated files verbatim (1:1) to wiki_dir/raw/repos/<repo_name>/...
    and deletes removed files.
    Returns list of modified or deleted file paths.
    """
    target_repo_dir = wiki_dir / "raw" / "repos" / repo_name
    touched: List[Path] = []

    # Write 1:1 files
    for rel_path, content in files_content.items():
        file_dest = target_repo_dir / rel_path
        file_dest.parent.mkdir(parents=True, exist_ok=True)
        file_dest.write_bytes(content)
        touched.append(file_dest)

    # Delete removed files
    for rel_path in files_to_delete:
        file_dest = target_repo_dir / rel_path
        if file_dest.exists():
            file_dest.unlink()
            touched.append(file_dest)
            # Clean up empty parent directories up to target_repo_dir
            parent = file_dest.parent
            while parent != target_repo_dir and parent.exists():
                if not any(parent.iterdir()):
                    parent.rmdir()
                    parent = parent.parent
                else:
                    break

    return touched
