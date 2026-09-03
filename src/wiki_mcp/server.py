from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

from wiki_mcp.core import extract_snippet, parse_frontmatter, resolve_page_path


def create_server(wiki_dir: Path) -> MCPServer:
    """Create and configure the read-only MCP server for the target wiki."""
    wiki_dir = wiki_dir.resolve()
    server = MCPServer(f"LLM-Wiki ({wiki_dir.name})")

    # -------------------------------------------------------------
    # 1. READ ORIENTATION
    # -------------------------------------------------------------
    @server.tool()
    def read_orientation() -> Dict[str, Any]:
        """
        Reads SCHEMA.md, index.md, and the last 30 lines of log.md
        in a single call for instant agent orientation.
        """
        schema_file = wiki_dir / "SCHEMA.md"
        index_file = wiki_dir / "index.md"
        log_file = wiki_dir / "log.md"

        schema_text = schema_file.read_text(encoding="utf-8") if schema_file.exists() else "SCHEMA.md not found."
        index_text = index_file.read_text(encoding="utf-8") if index_file.exists() else "index.md not found."

        recent_logs: List[str] = []
        if log_file.exists():
            lines = log_file.read_text(encoding="utf-8").splitlines()
            recent_logs = lines[-30:]

        return {
            "wiki_path": str(wiki_dir),
            "schema": schema_text,
            "index": index_text,
            "recent_activity_log": "\n".join(recent_logs),
        }

    # -------------------------------------------------------------
    # 2. SEARCH WIKI
    # -------------------------------------------------------------
    @server.tool()
    def search_wiki(query: str, tag: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Searches content and frontmatter across concepts/, entities/, comparisons/, and queries/.
        Optionally filters results by taxonomy tag.
        """
        results: List[Dict[str, Any]] = []
        query_lower = query.lower()
        tag_lower = tag.lower() if tag else None

        for folder_name in ["concepts", "entities", "comparisons", "queries"]:
            folder = wiki_dir / folder_name
            if not folder.exists() or not folder.is_dir():
                continue

            for file in folder.glob("*.md"):
                content = file.read_text(encoding="utf-8")
                metadata, body = parse_frontmatter(content)

                # Tag filter check
                if tag_lower:
                    raw_tags = metadata.get("tags", [])
                    if isinstance(raw_tags, list):
                        tag_match = any(tag_lower == str(t).lower() for t in raw_tags)
                    else:
                        tag_match = tag_lower in str(raw_tags).lower()
                    if not tag_match:
                        continue

                # Query match check against title, tags, or body text
                title = metadata.get("title", file.stem)
                tags_str = str(metadata.get("tags", ""))
                match_found = (
                    query_lower in body.lower()
                    or query_lower in str(title).lower()
                    or query_lower in tags_str.lower()
                )

                if match_found:
                    results.append({
                        "path": file.relative_to(wiki_dir).as_posix(),
                        "title": title,
                        "tags": metadata.get("tags", []),
                        "snippet": extract_snippet(body, query),
                    })

        return results

    # -------------------------------------------------------------
    # 3. GET PAGE
    # -------------------------------------------------------------
    @server.tool()
    def get_page(slug_or_path: str) -> Dict[str, Any]:
        """
        Returns the content and parsed YAML frontmatter of any page.
        Accepts direct paths (e.g. 'concepts/transformer.md') or simple slugs ('transformer').
        """
        target_file = resolve_page_path(wiki_dir, slug_or_path)
        if not target_file:
            return {"error": f"Page '{slug_or_path}' not found in wiki."}

        content = target_file.read_text(encoding="utf-8")
        metadata, body = parse_frontmatter(content)

        return {
            "path": target_file.relative_to(wiki_dir).as_posix(),
            "frontmatter": metadata,
            "content": body,
        }

    return server
