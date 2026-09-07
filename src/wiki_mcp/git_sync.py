import asyncio
import hashlib
import hmac
import os
import subprocess
from pathlib import Path
from typing import Optional, Tuple
from wiki_mcp.logger import get_logger, log_event

logger = get_logger("wiki_mcp.git_sync")


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
    try:
        res = subprocess.run(
            ["git", "-C", str(wiki_dir), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return "unknown"


def ensure_git_repo(wiki_dir: Path, repo_url: Optional[str] = None) -> None:
    """
    Startup initialization:
    - If .git exists, performs a fast-forward pull.
    - If .git is absent and repo_url is provided, performs a shallow clone.
    """
    wiki_dir = wiki_dir.resolve()
    git_dir = wiki_dir / ".git"

    if git_dir.exists():
        log_event(logger, 20, "git_sync_startup", f"Updating existing wiki mirror at {wiki_dir}")
        try:
            res = subprocess.run(
                ["git", "-C", str(wiki_dir), "pull", "--ff-only"],
                capture_output=True,
                text=True,
                check=True,
            )
            commit = get_current_commit(wiki_dir)
            log_event(logger, 20, "git_sync_startup_success", f"Updated to commit {commit}", output=res.stdout.strip())
        except subprocess.CalledProcessError as e:
            log_event(logger, 30, "git_sync_startup_warning", f"git pull failed: {e.stderr.strip()}")
    elif repo_url:
        log_event(logger, 20, "git_clone_startup", f"Cloning shallow mirror from {repo_url} into {wiki_dir}")
        wiki_dir.mkdir(parents=True, exist_ok=True)
        try:
            res = subprocess.run(
                ["git", "clone", "--depth", "50", repo_url, str(wiki_dir)],
                capture_output=True,
                text=True,
                check=True,
            )
            commit = get_current_commit(wiki_dir)
            log_event(logger, 20, "git_clone_startup_success", f"Cloned at commit {commit}")
        except subprocess.CalledProcessError as e:
            log_event(logger, 40, "git_clone_startup_error", f"git clone failed: {e.stderr.strip()}")
            raise RuntimeError(f"Failed to clone wiki repository: {e.stderr.strip()}") from e
    else:
        log_event(logger, 20, "git_sync_local_mode", f"Running on local folder without git remote: {wiki_dir}")


async def pull_repo_async(wiki_dir: Path) -> Tuple[bool, str, str]:
    """
    Asynchronously pulls upstream changes using git pull --ff-only.
    Returns (success, new_commit, output_message).
    """
    log_event(logger, 20, "git_pull_start", f"Triggering git pull in {wiki_dir}")
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", str(wiki_dir), "pull", "--ff-only",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        success = proc.returncode == 0
        output = (stdout if success else stderr).decode("utf-8").strip()
        commit = get_current_commit(wiki_dir)

        if success:
            log_event(logger, 20, "git_pull_success", f"Synced to commit {commit}", output=output)
        else:
            log_event(logger, 40, "git_pull_failed", f"Failed to pull: {output}", returncode=proc.returncode)

        return success, commit, output
    except Exception as e:
        log_event(logger, 40, "git_pull_exception", f"Exception during git pull: {str(e)}")
        return False, "unknown", str(e)
