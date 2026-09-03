import argparse
import os
import sys
from pathlib import Path
from wiki_mcp.server import create_server


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
    args = parser.parse_args()

    wiki_path_str = args.wiki_dir or os.getenv("WIKI_PATH", ".")
    wiki_path = Path(wiki_path_str).expanduser().resolve()

    if not wiki_path.exists() or not wiki_path.is_dir():
        sys.stderr.write(f"Error: Target wiki directory does not exist or is not a directory: {wiki_path}\n")
        sys.exit(1)

    server = create_server(wiki_path)
    server.run()


if __name__ == "__main__":
    main()
