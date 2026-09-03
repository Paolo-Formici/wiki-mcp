import tempfile
from pathlib import Path
from wiki_mcp.core import parse_frontmatter, resolve_page_path, is_safe_path, extract_snippet
from wiki_mcp.server import create_server


def test_parse_frontmatter():
    text_with_meta = """---
title: Sample Page
type: concept
tags: [ai, deep-learning]
---
# Hello World
This is sample content."""
    meta, body = parse_frontmatter(text_with_meta)
    assert meta["title"] == "Sample Page"
    assert meta["type"] == "concept"
    assert "ai" in meta["tags"]
    assert body.startswith("# Hello World")

    # Plain text without frontmatter
    plain = "Just content"
    meta_plain, body_plain = parse_frontmatter(plain)
    assert meta_plain == {}
    assert body_plain == "Just content"


def test_path_resolution_and_security():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        concepts = tmp_path / "concepts"
        concepts.mkdir()
        (concepts / "test-concept.md").write_text("hello", encoding="utf-8")

        # Direct path
        found = resolve_page_path(tmp_path, "concepts/test-concept.md")
        assert found is not None
        assert found.name == "test-concept.md"

        # Slug resolution
        found_slug = resolve_page_path(tmp_path, "test-concept")
        assert found_slug is not None
        assert found_slug.name == "test-concept.md"

        # Directory traversal blocked
        traversal = resolve_page_path(tmp_path, "../../etc/passwd")
        assert traversal is None


def test_snippet_extraction():
    text = "The quick brown fox jumps over the lazy dog."
    snippet = extract_snippet(text, "fox", max_chars=20)
    assert "fox" in snippet


def test_server_tools():
    with tempfile.TemporaryDirectory() as tmp:
        wiki = Path(tmp)
        (wiki / "SCHEMA.md").write_text("# Schema Rules", encoding="utf-8")
        (wiki / "index.md").write_text("# Index\n- [[test-entity]]", encoding="utf-8")
        (wiki / "log.md").write_text("entry 1\nentry 2", encoding="utf-8")

        entities = wiki / "entities"
        entities.mkdir()
        (entities / "test-entity.md").write_text("""---
title: Test Entity
tags: [model]
---
Body text discussing transformer models.""", encoding="utf-8")

        server = create_server(wiki)
        # Find tools
        tools = {tool.name: tool for tool in server._tool_manager.list_tools()}
        assert "read_orientation" in tools
        assert "search_wiki" in tools
        assert "get_page" in tools
