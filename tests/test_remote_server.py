import hashlib
import hmac
import tempfile
from pathlib import Path
import pytest
from starlette.testclient import TestClient
from wiki_mcp.remote import create_remote_server, get_streamable_app


@pytest.fixture
def temp_wiki():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        (p / "SCHEMA.md").write_text("# Schema Rules")
        (p / "index.md").write_text("# Index\n- [[test]]")
        (p / "log.md").write_text("log line 1\nlog line 2")
        yield p


def test_health_check_public(temp_wiki):
    server = create_remote_server(temp_wiki, auth_token="secret-token")
    app = get_streamable_app(server, auth_token="secret-token")

    with TestClient(app) as client:
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "healthy"


def test_auth_middleware_blocks_unauthorized(temp_wiki):
    server = create_remote_server(temp_wiki, auth_token="secret-token")
    app = get_streamable_app(server, auth_token="secret-token")

    with TestClient(app) as client:
        # /mcp without token should be 401
        res = client.post("/mcp", json={})
        assert res.status_code == 401

        # /mcp with bad token should be 401
        res = client.post("/mcp", json={}, headers={"Authorization": "Bearer bad-token"})
        assert res.status_code == 401

        # /mcp with good token passes auth middleware (reaches MCP handler)
        res = client.post("/mcp", json={}, headers={"Authorization": "Bearer secret-token"})
        assert res.status_code != 401


def test_webhook_endpoint(temp_wiki):
    webhook_secret = "webhook-key"
    server = create_remote_server(temp_wiki, webhook_secret=webhook_secret)
    app = get_streamable_app(server)

    payload = b'{"ref": "refs/heads/main"}'

    with TestClient(app) as client:
        # Missing signature -> 401
        res = client.post("/webhook", content=payload)
        assert res.status_code == 401

        # Valid GitHub signature
        sig = "sha256=" + hmac.new(webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
        res = client.post("/webhook", content=payload, headers={"X-Hub-Signature-256": sig})
        # Will attempt git pull and return status (200 or 500 if temp dir has no remote origin)
        assert res.status_code in [200, 500]


def test_health_check_sync_metadata(temp_wiki):
    # Without cron (default: webhook mode)
    server_webhook = create_remote_server(temp_wiki)
    app_webhook = get_streamable_app(server_webhook)
    with TestClient(app_webhook) as client:
        res = client.get("/health")
        data = res.json()
        assert data["sync"]["mode"] == "webhook"
        assert data["sync"]["cron_enabled"] is False
        assert data["sync"]["cron_expression"] is None

    # With cron (hybrid mode)
    server_cron = create_remote_server(temp_wiki, sync_cron="*/10 * * * *", webhook_secret="secret")
    app_cron = get_streamable_app(server_cron)
    with TestClient(app_cron) as client:
        res = client.get("/health")
        data = res.json()
        assert data["sync"]["mode"] == "hybrid"
        assert data["sync"]["cron_enabled"] is True
        assert data["sync"]["cron_expression"] == "*/10 * * * *"


def test_remote_app_lifespan_manages_scheduler(temp_wiki):
    server = create_remote_server(temp_wiki, sync_cron="*/15 * * * *")
    scheduler = getattr(server, "_cron_scheduler")
    assert scheduler is not None
    assert scheduler._task is None

    app = get_streamable_app(server)
    with TestClient(app):
        # Inside context, scheduler should be running
        assert scheduler._running is True
        assert scheduler._task is not None
        assert not scheduler._task.done()

    # Outside context, scheduler should be stopped
    assert scheduler._running is False
    assert scheduler._task is None

