import argparse
import os
import sys
from pathlib import Path
from wiki_mcp.logger import get_logger, log_event
from wiki_mcp.remote import create_remote_server, get_streamable_app
from wiki_mcp.server import create_server

logger = get_logger("wiki_mcp.cli")


def main():
    parser = argparse.ArgumentParser(
        prog="wiki-mcp",
        description="Fast, read-only MCP server for Karpathy-style LLM markdown wikis."
    )
    parser.add_argument(
        "--wiki-dir",
        type=Path,
        default=None,
        help="Target wiki directory path (defaults to WIKI_PATH env var or current directory)"
    )
    parser.add_argument(
        "--remote",
        action="store_true",
        default=os.getenv("REMOTE_MODE", "").lower() in ["1", "true", "yes"],
        help="Run as a remote HTTP server using Streamable HTTP transport"
    )
    parser.add_argument(
        "--host",
        type=str,
        default=os.getenv("HOST", "0.0.0.0"),
        help="Host to bind for remote server (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", "8000")),
        help="Port to listen on for remote server (default: 8000)"
    )
    parser.add_argument(
        "--git-url",
        type=str,
        default=os.getenv("WIKI_GIT_URL", None),
        help="Git repository URL to clone on startup if wiki directory is empty"
    )
    parser.add_argument(
        "--auth-token",
        type=str,
        default=os.getenv("AUTH_TOKEN", None),
        help="Bearer token required for MCP endpoints (optional)"
    )
    parser.add_argument(
        "--webhook-secret",
        type=str,
        default=os.getenv("WIKI_WEBHOOK_SECRET", None),
        help="Secret for validating GitHub/GitLab webhook signatures"
    )
    parser.add_argument(
        "--github-token",
        type=str,
        default=os.getenv("GITHUB_TOKEN", None),
        help="GitHub API token for fetching files from team repos verbatim (optional)"
    )
    parser.add_argument(
        "--repo-webhook-secret",
        type=str,
        default=os.getenv("REPO_WEBHOOK_SECRET", None),
        help="Secret for validating team repo webhook signatures (optional)"
    )
    parser.add_argument(
        "--allowed-repos",
        type=str,
        default=os.getenv("ALLOWED_REPOS", None),
        help="Comma-separated list of allowed repo names (e.g. repo1,org/repo2)"
    )
    parser.add_argument(
        "--git-branch",
        type=str,
        default=os.getenv("WIKI_GIT_BRANCH", "main"),
        help="Target git branch to push synced docs to (default: main)"
    )
    parser.add_argument(
        "--sync-cron",
        type=str,
        default=os.getenv("SYNC_CRON", None),
        help="Standard 5-field cron expression for periodic git pull (e.g. '*/5 * * * *', remote mode only)"
    )

    args = parser.parse_args()

    wiki_path_str = args.wiki_dir or os.getenv("WIKI_PATH", ".")
    wiki_path = Path(wiki_path_str).expanduser().resolve()

    if args.remote:
        allowed_list = [r.strip() for r in args.allowed_repos.split(",")] if args.allowed_repos else None
        log_event(
            logger, 20, "server_startup",
            f"Starting remote Wiki MCP server on {args.host}:{args.port}",
            wiki_dir=str(wiki_path), auth_enabled=bool(args.auth_token)
        )
        server = create_remote_server(
            wiki_dir=wiki_path,
            repo_url=args.git_url,
            webhook_secret=args.webhook_secret,
            auth_token=args.auth_token,
            github_token=args.github_token,
            repo_webhook_secret=args.repo_webhook_secret,
            allowed_repos=allowed_list,
            git_branch=args.git_branch,
            sync_cron=args.sync_cron,
        )

        app = get_streamable_app(server, auth_token=args.auth_token)

        import uvicorn
        uvicorn.run(app, host=args.host, port=args.port, log_config=None)
    else:
        # Standard local stdio mode
        if args.sync_cron:
            sys.stderr.write("Notice: --sync-cron is only active in --remote mode and ignored in local stdio mode.\n")
        if not wiki_path.exists() or not wiki_path.is_dir():
            sys.stderr.write(f"Error: Target wiki directory not found: {wiki_path}\n")
            sys.exit(1)
        server = create_server(wiki_path)
        server.run()


if __name__ == "__main__":
    main()
