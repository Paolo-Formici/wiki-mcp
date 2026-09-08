import asyncio
import hashlib
import hmac
import subprocess
from pathlib import Path
from typing import Optional, Tuple
from wiki_mcp.logger import get_logger, log_event

from dataclasses import dataclass
from datetime import datetime, timezone

logger = get_logger("wiki_mcp.git_sync")

_pull_lock = asyncio.Lock()


@dataclass
class SyncMetadata:
    last_sync_at: Optional[str] = None
    last_sync_status: str = "idle"
    last_sync_trigger: Optional[str] = None
    last_sync_commit: Optional[str] = None
    last_sync_error: Optional[str] = None


_sync_metadata = SyncMetadata()


def get_sync_metadata() -> SyncMetadata:
    """Returns the current sync metadata."""
    return _sync_metadata


def git_cmd(wiki_dir: Path, *args: str) -> Tuple[int, str, str]:
    """Runs a git command synchronously."""
    res = subprocess.run(
        ["git", "-C", str(wiki_dir), *args],
        capture_output=True,
        text=True,
    )
    return res.returncode, res.stdout.strip(), res.stderr.strip()


async def git_cmd_async(wiki_dir: Path, *args: str) -> Tuple[int, str, str]:
    """Runs a git command in a thread without blocking the async event loop."""
    return await asyncio.to_thread(git_cmd, wiki_dir, *args)


def verify_github_signature(payload_bytes: bytes, signature_header: Optional[str], secret: str) -> bool:
    """Constant-time validation of GitHub X-Hub-Signature-256 HMAC."""
    if not secret or not signature_header:
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature_header, expected)


def verify_gitlab_token(token_header: Optional[str], secret: str) -> bool:
    """Constant-time validation of GitLab X-Gitlab-Token."""
    if not secret or not token_header:
        return False
    return hmac.compare_digest(token_header, secret)


def get_current_commit(wiki_dir: Path) -> str:
    """Returns the current short commit hash of the wiki repo."""
    code, out, _ = git_cmd(wiki_dir, "rev-parse", "--short", "HEAD")
    return out if code == 0 else "unknown"


def ensure_git_repo(wiki_dir: Path, repo_url: Optional[str] = None) -> None:
    """
    Startup initialization:
    - If .git exists, performs a fast-forward pull.
    - If .git is absent and repo_url is provided, performs a shallow clone.
    """
    wiki_dir = wiki_dir.resolve()
    git_dir = wiki_dir / ".git"
    now_iso = datetime.now(timezone.utc).isoformat()

    if git_dir.exists():
        log_event(logger, 20, "git_sync_startup", f"Updating existing wiki mirror at {wiki_dir}")
        code, out, err = git_cmd(wiki_dir, "pull", "--ff-only")
        commit = get_current_commit(wiki_dir)
        _sync_metadata.last_sync_at = now_iso
        _sync_metadata.last_sync_trigger = "startup"
        _sync_metadata.last_sync_commit = commit
        if code == 0:
            _sync_metadata.last_sync_status = "synced"
            _sync_metadata.last_sync_error = None
            log_event(logger, 20, "git_sync_startup_success", f"Updated to commit {commit}", output=out)
        else:
            _sync_metadata.last_sync_status = "failed"
            _sync_metadata.last_sync_error = err
            log_event(logger, 30, "git_sync_startup_warning", f"git pull failed: {err}")
    elif repo_url:
        log_event(logger, 20, "git_clone_startup", f"Cloning shallow mirror from {repo_url} into {wiki_dir}")
        wiki_dir.mkdir(parents=True, exist_ok=True)
        res = subprocess.run(
            ["git", "clone", "--depth", "50", repo_url, str(wiki_dir)],
            capture_output=True,
            text=True,
        )
        commit = get_current_commit(wiki_dir)
        _sync_metadata.last_sync_at = now_iso
        _sync_metadata.last_sync_trigger = "startup"
        _sync_metadata.last_sync_commit = commit
        if res.returncode == 0:
            _sync_metadata.last_sync_status = "synced"
            _sync_metadata.last_sync_error = None
            log_event(logger, 20, "git_clone_startup_success", f"Cloned at commit {commit}")
        else:
            err = res.stderr.strip()
            _sync_metadata.last_sync_status = "failed"
            _sync_metadata.last_sync_error = err
            log_event(logger, 40, "git_clone_startup_error", f"git clone failed: {err}")
            raise RuntimeError(f"Failed to clone wiki repository: {err}")
    else:
        commit = get_current_commit(wiki_dir)
        _sync_metadata.last_sync_commit = commit
        log_event(logger, 20, "git_sync_local_mode", f"Running on local folder without git remote: {wiki_dir}")


async def pull_repo_async(wiki_dir: Path, trigger: str = "webhook") -> Tuple[bool, str, str]:
    """
    Asynchronously pulls upstream changes using git pull --ff-only.
    Acquires _pull_lock to serialize concurrent pulls.
    Updates sync metadata.
    Returns (success, new_commit, output_message).
    """
    async with _pull_lock:
        log_event(logger, 20, "git_pull_start", f"Triggering git pull in {wiki_dir} (trigger={trigger})")
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            code, out, err = await git_cmd_async(wiki_dir, "pull", "--ff-only")
            commit = get_current_commit(wiki_dir)
            output = out if code == 0 else err

            _sync_metadata.last_sync_at = now_iso
            _sync_metadata.last_sync_trigger = trigger
            _sync_metadata.last_sync_commit = commit

            if code == 0:
                _sync_metadata.last_sync_status = "synced"
                _sync_metadata.last_sync_error = None
                log_event(logger, 20, "git_pull_success", f"Synced to commit {commit}", output=output, trigger=trigger)
                return True, commit, output
            else:
                _sync_metadata.last_sync_status = "failed"
                _sync_metadata.last_sync_error = output
                log_event(logger, 40, "git_pull_failed", f"Failed to pull: {output}", returncode=code, trigger=trigger)
                return False, commit, output
        except Exception as e:
            _sync_metadata.last_sync_at = now_iso
            _sync_metadata.last_sync_status = "failed"
            _sync_metadata.last_sync_trigger = trigger
            _sync_metadata.last_sync_error = str(e)
            log_event(logger, 40, "git_pull_exception", f"Exception during git pull: {str(e)}", trigger=trigger)
            return False, "unknown", str(e)


async def commit_and_push_async(
    wiki_dir: Path,
    target_rel_path: str,
    commit_message: str,
    branch: str = "main",
    max_retries: int = 3,
) -> Tuple[bool, str]:
    """
    Stages target_rel_path, commits if changes exist, and pushes to remote.
    Uses '--rebase' retry strategy if remote advanced during sync.
    """
    git_dir = wiki_dir / ".git"
    if not git_dir.exists():
        log_event(logger, 20, "git_push_skipped", f"No .git directory in {wiki_dir}; skipping commit/push")
        return True, "No git repository found; changes kept on disk."

    try:
        # 1. Stage changes
        code, _, err = await git_cmd_async(wiki_dir, "add", target_rel_path)
        if code != 0:
            log_event(logger, 40, "git_add_failed", f"git add failed: {err}")
            return False, f"git add failed: {err}"

        # 2. Check status
        code, status_out, _ = await git_cmd_async(wiki_dir, "status", "--porcelain", target_rel_path)
        if not status_out:
            log_event(logger, 20, "git_commit_skipped", f"No changes to commit for {target_rel_path}")
            return True, "No changes detected."

        # 3. Commit with bot author
        code, _, err = await git_cmd_async(
            wiki_dir,
            "-c", "user.name=Wiki Bot",
            "-c", "user.email=bot@dev-wiki.internal",
            "commit", "-m", commit_message,
        )
        if code != 0:
            log_event(logger, 40, "git_commit_failed", f"git commit failed: {err}")
            return False, f"git commit failed: {err}"

        # 4. Push with retry and rebase
        last_err = ""
        for attempt in range(1, max_retries + 1):
            log_event(logger, 20, "git_push_attempt", f"Pushing changes (attempt {attempt}/{max_retries})")
            code, out, err = await git_cmd_async(wiki_dir, "push", "origin", branch)
            if code == 0:
                log_event(logger, 20, "git_push_success", "Pushed changes successfully to remote")
                return True, out

            last_err = err
            log_event(logger, 30, "git_push_rejected", f"Push rejected: {err}; pulling with rebase")
            code_reb, _, err_reb = await git_cmd_async(wiki_dir, "pull", "--rebase", "origin", branch)
            if code_reb != 0:
                log_event(logger, 40, "git_rebase_failed", f"Rebase failed during push retry: {err_reb}")
                return False, f"Push rejected and rebase failed: {err_reb}"

        return False, f"Failed to push after {max_retries} attempts: {last_err}"

    except Exception as e:
        log_event(logger, 40, "git_push_exception", f"Exception during git commit/push: {str(e)}")
        return False, str(e)
