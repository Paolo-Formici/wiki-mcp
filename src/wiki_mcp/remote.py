import hmac
import time
from pathlib import Path
from typing import List, Optional
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

from wiki_mcp.git_sync import (
    ensure_git_repo,
    get_current_commit,
    pull_repo_async,
    verify_github_signature,
    verify_gitlab_token,
)
from wiki_mcp.logger import get_logger, log_event
from wiki_mcp.server import create_server

logger = get_logger("wiki_mcp.remote")


class TokenAuthMiddleware(BaseHTTPMiddleware):
    """
    Validates Bearer token on MCP endpoints if auth_token is configured.
    Public endpoints (/health, /webhook) bypass this check.
    """

    def __init__(self, app: ASGIApp, auth_token: Optional[str] = None):
        super().__init__(app)
        self.auth_token = auth_token

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        # Health checks and webhooks handle their own authentication/openness
        if not self.auth_token or path in ["/health", "/webhook"]:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            log_event(
                logger, 30, "auth_failed", "Missing or malformed Authorization header",
                path=path, client=request.client.host if request.client else "unknown"
            )
            return JSONResponse({"error": "Unauthorized: Missing Bearer token"}, status_code=401)

        token = auth_header[7:].strip()
        if not hmac.compare_digest(token, self.auth_token):
            log_event(
                logger, 30, "auth_failed", "Invalid Bearer token provided",
                path=path, client=request.client.host if request.client else "unknown"
            )
            return JSONResponse({"error": "Unauthorized: Invalid token"}, status_code=401)

        return await call_next(request)


def create_remote_server(
    wiki_dir: Path,
    repo_url: Optional[str] = None,
    webhook_secret: Optional[str] = None,
    auth_token: Optional[str] = None,
) -> MCPServer:
    """Configures the MCPServer with Git synchronization, health checks, and webhooks."""
    wiki_dir = wiki_dir.resolve()
    ensure_git_repo(wiki_dir, repo_url)

    server = create_server(wiki_dir)

    # -------------------------------------------------------------
    # 1. HEALTH PROBE (/health)
    # -------------------------------------------------------------
    @server.custom_route("/health", methods=["GET"])
    async def health_check(request: Request) -> Response:
        """Liveness & readiness probe for load balancers and orchestrators."""
        commit = get_current_commit(wiki_dir)
        return JSONResponse({
            "status": "healthy",
            "wiki": str(wiki_dir),
            "commit": commit,
        })

    # -------------------------------------------------------------
    # 2. WEBHOOK ENDPOINT (/webhook)
    # -------------------------------------------------------------
    @server.custom_route("/webhook", methods=["POST"])
    async def git_webhook(request: Request) -> Response:
        """
        Inbound webhook endpoint for GitHub (X-Hub-Signature-256) and GitLab (X-Gitlab-Token).
        Triggers an immediate fast-forward git pull.
        """
        body_bytes = await request.body()

        # Validate secret if configured
        if webhook_secret:
            gh_sig = request.headers.get("X-Hub-Signature-256")
            gl_token = request.headers.get("X-Gitlab-Token")

            valid_gh = verify_github_signature(body_bytes, gh_sig, webhook_secret)
            valid_gl = verify_gitlab_token(gl_token, webhook_secret)

            if not (valid_gh or valid_gl):
                log_event(logger, 30, "webhook_auth_failed", "Invalid webhook signature or token")
                return JSONResponse({"error": "Invalid webhook signature"}, status_code=401)

        # Execute async git pull
        start_time = time.time()
        success, commit, output = await pull_repo_async(wiki_dir)
        duration_ms = round((time.time() - start_time) * 1000, 2)

        if not success:
            return JSONResponse({"status": "error", "error": output, "commit": commit}, status_code=500)

        return JSONResponse({
            "status": "synced",
            "commit": commit,
            "output": output,
            "duration_ms": duration_ms,
        })

    return server


def get_streamable_app(
    server: MCPServer,
    auth_token: Optional[str] = None,
    allowed_hosts: Optional[List[str]] = None,
) -> Starlette:
    """Builds the Starlette ASGI app with configured security and authentication."""
    try:
        from mcp.server.transport_security import TransportSecuritySettings
        security = TransportSecuritySettings(
            enable_dns_rebinding_protection=bool(allowed_hosts),
            allowed_hosts=allowed_hosts or [],
        )
        app = server.streamable_http_app(transport_security=security)
    except Exception:
        app = server.streamable_http_app()

    if auth_token:
        app.add_middleware(TokenAuthMiddleware, auth_token=auth_token)

    return app
