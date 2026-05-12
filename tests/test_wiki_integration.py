"""Integration tests for wiki-mcp knowledge system integration.

Tests verify: config settings, MCP client registration, SKILL.md validity,
and agent tool availability.
"""
import pytest
from pathlib import Path
import yaml

SKILLS_DIR = Path("src/app/skills")


class TestWikiConfig:
    """D-08: wiki-mcp settings in config.py."""

    def test_config_has_wiki_mcp_command(self):
        from app.core.config import Settings
        s = Settings()
        assert hasattr(s, "wiki_mcp_command")
        assert s.wiki_mcp_command == "npx"

    def test_config_has_wiki_mcp_args(self):
        from app.core.config import Settings
        s = Settings()
        assert hasattr(s, "wiki_mcp_args")
        assert "tsx" in s.wiki_mcp_args
        assert "wiki-mcp" in s.wiki_mcp_args

    def test_config_has_wiki_mcp_config_path(self):
        from app.core.config import Settings
        s = Settings()
        assert hasattr(s, "wiki_mcp_config_path")
        assert "wiki-mcp-config.json" in s.wiki_mcp_config_path


class TestWikiMCPClient:
    """D-04: wiki-mcp stdio registration in mcp_client.py."""

    def test_mcp_client_imports(self):
        from app.mcp.mcp_client import get_mcp_client
        assert callable(get_mcp_client)

    def test_mcp_client_config_structure(self):
        """Verify mcp_client.py references wiki-mcp (source-level check)."""
        content = Path("src/app/mcp/mcp_client.py").read_text(encoding="utf-8")
        assert "wiki-mcp" in content, "Missing wiki-mcp server entry"
        assert "stdio" in content, "Missing stdio transport"


class TestWikiSkill:
    """D-06: wiki-query SKILL.md validity."""

    def test_wiki_skill_directory_exists(self):
        assert (SKILLS_DIR / "wiki-query").is_dir()

    def test_wiki_skill_md_exists(self):
        assert (SKILLS_DIR / "wiki-query" / "SKILL.md").is_file()

    def test_wiki_skill_frontmatter_valid(self):
        content = (SKILLS_DIR / "wiki-query" / "SKILL.md").read_text(encoding="utf-8")
        parts = content.split("---", 2)
        assert len(parts) >= 3, "Missing YAML frontmatter delimiters"
        fm = yaml.safe_load(parts[1])
        assert fm["name"] == "wiki-query", f"Name mismatch: {fm.get('name')}"
        assert len(fm["description"]) > 20, "Description too short"

    def test_wiki_skill_has_all_tools(self):
        """D-05: SKILL.md must reference all 6 wiki-mcp tools."""
        content = (SKILLS_DIR / "wiki-query" / "SKILL.md").read_text(encoding="utf-8")
        expected_tools = ["search", "get_page", "list_pages", "list_wikis", "graph_query", "reload"]
        for tool in expected_tools:
            assert tool in content, f"Missing tool reference: {tool}"

    def test_wiki_skill_has_workflow_integration(self):
        """D-07: SKILL.md must reference requirement-analysis and test-strategy stages."""
        content = (SKILLS_DIR / "wiki-query" / "SKILL.md").read_text(encoding="utf-8")
        assert "requirement-analysis" in content or "需求分析" in content, "Missing requirement-analysis reference"
        assert "test-strategy" in content or "测试策略" in content, "Missing test-strategy reference"

    def test_wiki_skill_sufficient_content(self):
        content = (SKILLS_DIR / "wiki-query" / "SKILL.md").read_text(encoding="utf-8")
        assert len(content) > 500, f"Content too short: {len(content)} chars"


class TestAllSkills:
    """Verify all 6 skills (5 existing + wiki-query) are discoverable."""

    def test_all_skill_dirs_present(self):
        expected = ["requirement-analysis", "test-strategy", "test-case-design",
                     "quality-review", "output-formatter", "wiki-query"]
        actual = {d.name for d in SKILLS_DIR.iterdir() if d.is_dir()}
        for skill in expected:
            assert skill in actual, f"Missing skill directory: {skill}"
