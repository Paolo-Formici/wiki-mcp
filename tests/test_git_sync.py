import hashlib
import hmac
import tempfile
from pathlib import Path
from wiki_mcp.git_sync import (
    ensure_git_repo,
    get_current_commit,
    verify_github_signature,
    verify_gitlab_token,
)


def test_webhook_signatures():
    secret = "my-secret-key"
    payload = b'{"ref": "refs/heads/main"}'

    # Valid GitHub
    sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert verify_github_signature(payload, sig, secret) is True

    # Invalid GitHub
    assert verify_github_signature(payload, "sha256=invalid", secret) is False
    assert verify_github_signature(payload, None, secret) is False

    # Valid GitLab
    assert verify_gitlab_token("my-secret-key", secret) is True
    assert verify_gitlab_token("wrong-token", secret) is False


def test_git_init_and_commit():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        import subprocess
        subprocess.run(["git", "init"], cwd=str(p), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(p), check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(p), check=True)
        (p / "README.md").write_text("hello")
        subprocess.run(["git", "add", "."], cwd=str(p), check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(p), check=True, capture_output=True)

        commit = get_current_commit(p)
        assert len(commit) >= 4
        assert commit != "unknown"
