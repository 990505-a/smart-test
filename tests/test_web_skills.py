"""Tests for Web Agent Skills: SKILL.md readability and reference guides."""
import pytest
from pathlib import Path
from src.app.agents.web.tools import file_backend

WORKSPACE_SKILLS = Path(__file__).parent.parent / "workspace" / "web" / "skills"

REQUIRED_SKILLS = [
    "playwright-cli",
    "agent-browser",
    "agent-browser-vs-playwright-cli",
    "pw-dogfood",
    "component-aware-web-automation",
]


class TestSkillFiles:
    @pytest.mark.parametrize("skill_name", REQUIRED_SKILLS)
    def test_skill_md_exists(self, skill_name):
        skill_path = WORKSPACE_SKILLS / skill_name / "SKILL.md"
        assert skill_path.exists(), f"Missing SKILL.md for {skill_name}"

    @pytest.mark.parametrize("skill_name", REQUIRED_SKILLS)
    def test_skill_md_readable(self, skill_name):
        skill_path = WORKSPACE_SKILLS / skill_name / "SKILL.md"
        content = skill_path.read_text(encoding="utf-8")
        assert len(content) > 100, f"{skill_name}/SKILL.md too short"

    @pytest.mark.parametrize("skill_name", REQUIRED_SKILLS)
    def test_skill_via_filesystem_backend(self, skill_name):
        res = file_backend.read(f"/skills/{skill_name}/SKILL.md")
        assert not res.error, f"Backend error reading {skill_name}: {res.error}"


class TestReferenceGuides:
    AGENT_GUIDES = [
        "script-analyst-guide.md",
        "stage-manager-guide.md",
        "blocking-coach-guide.md",
        "set-designer-guide.md",
        "choreographer-guide.md",
        "assistant-director-guide.md",
        "continuity-lead-guide.md",
    ]

    @pytest.mark.parametrize("guide", AGENT_GUIDES)
    def test_agent_guide_exists(self, guide):
        path = WORKSPACE_SKILLS / "component-aware-web-automation" / "references" / guide
        assert path.exists(), f"Missing guide: {guide}"

    @pytest.mark.parametrize("guide", AGENT_GUIDES)
    def test_agent_guide_readable(self, guide):
        path = WORKSPACE_SKILLS / "component-aware-web-automation" / "references" / guide
        content = path.read_text(encoding="utf-8")
        assert len(content) > 50, f"{guide} too short"

    def test_pw_dogfood_references(self):
        refs = ["accessibility-testing.md", "issue-taxonomy.md", "performance-testing.md", "security-checks.md"]
        for ref in refs:
            path = WORKSPACE_SKILLS / "pw-dogfood" / "references" / ref
            assert path.exists(), f"Missing pw-dogfood reference: {ref}"

    def test_report_template_exists(self):
        path = WORKSPACE_SKILLS / "pw-dogfood" / "templates" / "report-template.md"
        assert path.exists(), "Missing report-template.md"
