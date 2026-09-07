import hashlib
import hmac
import json
import tempfile
from pathlib import Path
import pytest
from starlette.testclient import TestClient
from unittest.mock import AsyncMock, patch

from wiki_mcp.repo_sync import (
    extract_modified_doc_files,
    is_doc_file,
    sync_repo_docs_to_disk,
)
from wiki_mcp.remote import create_remote_server, get_streamable_app


def test_is_doc_file_matching():
    # Valid doc files
    assert is_doc_file("README.md")
    assert is_doc_file("readme.txt")
    assert is_doc_file("docs/architecture.md")
    assert is_doc_file("docs/api/v1/endpoints.md")
    assert is_doc_file("adr/001-record.adr.md")
    assert is_doc_file("openapi.yaml")
    assert is_doc_file("schema.graphql")
    assert is_doc_file("nested/path/README.md")

    # Ignored source code and dependencies
    assert not is_doc_file("src/main.py")
    assert not is_doc_file("app/controllers/user.ts")
    assert not is_doc_file("node_modules/express/README.md")
    assert not is_doc_file(".git/config")
    assert not is_doc_file("dist/bundle.js")


def test_extract_modified_doc_files():
    payload = {
        "repository": {
            "name": "payment-service",
            "full_name": "my-org/payment-service",
        },
        "after": "c0ffee1234567890",
        "commits": [
            {
                "added": ["README.md", "src/payment.py"],
                "modified": ["docs/architecture.md", "package.json"],
                "removed": ["old_docs/legacy.md"],
            }
        ],
    }

    repo, full_name, sha, to_sync, to_del = extract_modified_doc_files(payload)
    assert repo == "payment-service"
    assert full_name == "my-org/payment-service"
    assert sha == "c0ffee1234567890"
    assert "README.md" in to_sync
    assert "docs/architecture.md" in to_sync
    assert "src/payment.py" not in to_sync
    assert "old_docs/legacy.md" in to_del


def test_extract_modified_doc_files_allowed_repos_filter():
    payload = {
        "repository": {"name": "unauthorized-repo"},
        "after": "abc123",
        "commits": [{"added": ["README.md"]}],
    }
    repo, _, _, to_sync, _ = extract_modified_doc_files(payload, allowed_repos=["billing-service", "auth-service"])
    assert repo is None
    assert len(to_sync) == 0


def test_sync_repo_docs_to_disk():
    with tempfile.TemporaryDirectory() as tmp:
        wiki_dir = Path(tmp)
        files_content = {
            "README.md": b"# Payment Service\nVerbatim 1:1 content",
            "docs/architecture.md": b"# Arch Flow",
        }
        to_delete = set()

        touched = sync_repo_docs_to_disk(wiki_dir, "payment-service", files_content, to_delete)
        assert len(touched) == 2

        readme_path = wiki_dir / "raw" / "repos" / "payment-service" / "README.md"
        arch_path = wiki_dir / "raw" / "repos" / "payment-service" / "docs" / "architecture.md"

        assert readme_path.exists()
        assert readme_path.read_text() == "# Payment Service\nVerbatim 1:1 content"
        assert arch_path.exists()

        # Now test deletion
        touched_del = sync_repo_docs_to_disk(wiki_dir, "payment-service", {}, {"docs/architecture.md"})
        assert not arch_path.exists()
        assert readme_path.exists()


@pytest.fixture
def temp_wiki():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        (p / "SCHEMA.md").write_text("# Schema")
        (p / "index.md").write_text("# Index")
        yield p


def test_repo_sync_webhook_open_mode(temp_wiki):
    """When no webhook secret is configured (YAGNI), requests are accepted without HMAC."""
    server = create_remote_server(temp_wiki)
    app = get_streamable_app(server)

    payload = {
        "repository": {"name": "auth-service", "full_name": "org/auth-service"},
        "after": "9876543210abcdef",
        "commits": [
            {
                "added": ["README.md"],
                "modified": [],
                "removed": [],
            }
        ],
    }

    with patch("wiki_mcp.remote.fetch_github_file_async", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = b"# Auth Service Readme"
        with TestClient(app) as client:
            res = client.post("/webhook/repo-sync", json=payload)
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "synced"
            assert data["repo"] == "auth-service"
            assert "README.md" in data["synced_files"]

            # Check 1:1 file on disk
            synced_file = temp_wiki / "raw" / "repos" / "auth-service" / "README.md"
            assert synced_file.exists()
            assert synced_file.read_text() == "# Auth Service Readme"


def test_repo_sync_webhook_with_secret(temp_wiki):
    """When secret is configured, validates HMAC signature."""
    secret = "my-sync-secret"
    server = create_remote_server(temp_wiki, repo_webhook_secret=secret)
    app = get_streamable_app(server)

    payload = {
        "repository": {"name": "billing-service"},
        "after": "112233445566",
        "commits": [{"modified": ["docs/billing.md"]}],
    }
    payload_bytes = json.dumps(payload).encode("utf-8")

    with patch("wiki_mcp.remote.fetch_github_file_async", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = b"# Billing Specs"
        with TestClient(app) as client:
            # Unsigned -> 401
            res = client.post("/webhook/repo-sync", content=payload_bytes)
            assert res.status_code == 401

            # Signed -> 200
            sig = "sha256=" + hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
            res_ok = client.post(
                "/webhook/repo-sync",
                content=payload_bytes,
                headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
            )
            assert res_ok.status_code == 200
            assert res_ok.json()["status"] == "synced"


def test_repo_sync_skips_when_no_doc_changes(temp_wiki):
    server = create_remote_server(temp_wiki)
    app = get_streamable_app(server)

    payload = {
        "repository": {"name": "core-backend"},
        "after": "abcdef123456",
        "commits": [{"modified": ["src/main.rs", "src/lib.rs"]}],
    }

    with TestClient(app) as client:
        res = client.post("/webhook/repo-sync", json=payload)
        assert res.status_code == 200
        assert res.json()["status"] == "skipped"
