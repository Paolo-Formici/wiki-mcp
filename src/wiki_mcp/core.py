from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import yaml


def parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """
    Extract YAML frontmatter dictionary and markdown body.
    Safely falls back to empty metadata if frontmatter is missing or invalid.
    """
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                meta = yaml.safe_load(parts[1])
                if isinstance(meta, dict):
                    return meta, parts[2].strip()
            except yaml.YAMLError:
                pass
    return {}, content.strip()


def is_safe_path(base_dir: Path, target_path: Path) -> bool:
    """Verify that target_path is located inside base_dir to block path traversal."""
    try:
        target_path.resolve().relative_to(base_dir.resolve())
        return True
    except ValueError:
        return False


def resolve_page_path(wiki_dir: Path, slug_or_path: str) -> Optional[Path]:
    """
    Resolves a wiki page path safely.
    Handles direct paths ('concepts/transformer.md') or simple slugs ('transformer').
    """
    clean = slug_or_path.strip().removesuffix(".md")
    direct = (wiki_dir / f"{clean}.md").resolve()

    if direct.is_file() and is_safe_path(wiki_dir, direct):
        return direct

    # Search markdown files across wiki directories (excluding hidden paths like .git)
    return next(
        (
            p.resolve()
            for p in wiki_dir.glob(f"**/{clean}.md")
            if p.is_file()
            and not any(part.startswith(".") for part in p.parts)
            and is_safe_path(wiki_dir, p)
        ),
        None,
    )



def extract_snippet(text: str, query: str, max_chars: int = 250) -> str:
    """Extracts a short snippet of text surrounding the first match of query."""
    query_lower = query.lower()
    text_lower = text.lower()
    idx = text_lower.find(query_lower)

    if idx == -1:
        snippet = text[:max_chars].strip()
        return f"{snippet}..." if len(text) > max_chars else snippet

    half_window = max_chars // 2
    start = max(0, idx - half_window)
    end = min(len(text), idx + len(query) + half_window)

    snippet = text[start:end].replace("\n", " ").strip()
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{snippet}{suffix}"
