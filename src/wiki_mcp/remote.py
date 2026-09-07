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
    commit_and_push_async,
    ensure_git_repo,
    get_current_commit,
    pull_repo_async,
    verify_github_signature,
    verify_gitlab_token,
)
from wiki_mcp.logger import get_logger, log_event
from wiki_mcp.repo_sync import (
    extract_modified_doc_files,
    fetch_github_file_async,
    sync_repo_docs_to_disk,
)
from wiki_mcp.server import create_server

logger = get_logger("wiki_mcp.remote")


class TokenAuthMiddleware(BaseHTTPMiddleware):
    """
    Validates Bearer token on MCP endpoints if auth_token is configured.
    Public endpoints (/health, /webhook, /webhook/repo-sync) bypass this check.
    """

    def __init__(self, app: ASGIApp, auth_token: Optional[str] = None):
        super().__init__(app)
        self.auth_token = auth_token

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        # Health checks and webhooks handle their own authentication/openness
        if not self.auth_token or path in ["/health", "/webhook", "/webhook/repo-sync"]:
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
    github_token: Optional[str] = None,
    repo_webhook_secret: Optional[str] = None,
    allowed_repos: Optional[List[str]] = None,
    git_branch: str = "main",
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

    # -------------------------------------------------------------
    # 3. REPO SYNC WEBHOOK (/webhook/repo-sync)
    # -------------------------------------------------------------
    @server.custom_route("/webhook/repo-sync", methods=["POST"])
    async def repo_sync_webhook(request: Request) -> Response:
        """
        Inbound webhook endpoint for external team repositories.
        Selectively syncs documentation/contracts 1:1 into raw/repos/<repo_name>/,
        then commits and pushes back to dev-wiki remote.
        """
        body_bytes = await request.body()

        # Optional signature verification (YAGNI: only if repo_webhook_secret or webhook_secret is configured)
        secret = repo_webhook_secret or webhook_secret
        if secret:
            gh_sig = request.headers.get("X-Hub-Signature-256")
            gl_token = request.headers.get("X-Gitlab-Token")
            valid_gh = verify_github_signature(body_bytes, gh_sig, secret)
            valid_gl = verify_gitlab_token(gl_token, secret)
            if not (valid_gh or valid_gl):
                log_event(logger, 30, "repo_webhook_auth_failed", "Invalid webhook signature or token")
                return JSONResponse({"error": "Invalid webhook signature"}, status_code=401)

        try:
            import json
            payload = json.loads(body_bytes.decode("utf-8"))
        except Exception as e:
            return JSONResponse({"error": f"Invalid JSON payload: {str(e)}"}, status_code=400)

        repo_name, repo_full_name, commit_sha, files_to_sync, files_to_delete = extract_modified_doc_files(
            payload, allowed_repos=allowed_repos
        )

        if not repo_name or not commit_sha:
            return JSONResponse({
                "status": "skipped",
                "message": "Missing repository name or commit sha, or repo not allowed"
            }, status_code=200)

        if not files_to_sync and not files_to_delete:
            log_event(logger, 20, "repo_sync_no_docs", f"No doc files modified in {repo_name} at {commit_sha[:8]}")
            return JSONResponse({
                "status": "skipped",
                "repo": repo_name,
                "message": "No documentation files added, modified, or deleted in this commit",
            }, status_code=200)

        log_event(
            logger, 20, "repo_sync_start",
            f"Syncing docs for {repo_name} ({len(files_to_sync)} to sync, {len(files_to_delete)} to delete)",
            repo=repo_name, sync_count=len(files_to_sync), delete_count=len(files_to_delete)
        )

        # Fetch files verbatim 1:1
        files_content = {}
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            for file_path in files_to_sync:
                content = await fetch_github_file_async(
                    repo_full_name=repo_full_name,
                    file_path=file_path,
                    ref=commit_sha,
                    token=github_token,
                    client=client,
                )
                if content is not None:
                    files_content[file_path] = content

        # Write to disk
        touched = sync_repo_docs_to_disk(wiki_dir, repo_name, files_content, files_to_delete)

        # Commit and push
        commit_msg = f"chore(raw): sync {repo_name} docs from {commit_sha[:8]}"
        push_ok, push_output = await commit_and_push_async(
            wiki_dir=wiki_dir,
            target_rel_path=f"raw/repos/{repo_name}",
            commit_message=commit_msg,
            branch=git_branch,
        )

        return JSONResponse({
            "status": "synced",
            "repo": repo_name,
            "commit_sha": commit_sha,
            "synced_files": list(files_content.keys()),
            "deleted_files": list(files_to_delete),
            "pushed": push_ok,
            "git_output": push_output,
        })

    return server


def get_streamable_app(server: MCPServer, auth_token: Optional[str] = None) -> Starlette:
    """Builds the Starlette ASGI app with configured token authentication."""
    app = server.streamable_http_app()
    if auth_token:
        app.add_middleware(TokenAuthMiddleware, auth_token=auth_token)
    return app

