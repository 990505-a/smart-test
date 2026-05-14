"""Tests for API Agent Skills: SKILL.md files existence and content validation."""
import pytest
from pathlib import Path

WORKSPACE_SKILLS = Path(__file__).parent.parent / "workspace" / "default" / "api" / "skills"

REQUIRED_SKILLS = [
    "test-scenario-design",
    "playwright-api-testing",
    "api-test-quality",
]


def _read_skill(skill_name: str) -> str:
    """Read SKILL.md content for a given skill."""
    skill_path = WORKSPACE_SKILLS / skill_name / "SKILL.md"
    assert skill_path.exists(), f"Missing SKILL.md for {skill_name}"
    return skill_path.read_text(encoding="utf-8")


class TestSkillFiles:
    @pytest.mark.parametrize("skill_name", REQUIRED_SKILLS)
    def test_skill_md_exists(self, skill_name):
        """Each required skill directory must contain SKILL.md."""
        skill_path = WORKSPACE_SKILLS / skill_name / "SKILL.md"
        assert skill_path.exists(), f"Missing SKILL.md for {skill_name}"

    @pytest.mark.parametrize("skill_name", REQUIRED_SKILLS)
    def test_skill_md_readable(self, skill_name):
        """Each SKILL.md must have substantial content (>100 chars)."""
        content = _read_skill(skill_name)
        assert len(content) > 100, f"{skill_name}/SKILL.md too short"


class TestSkillFrontmatter:
    @pytest.mark.parametrize("skill_name", REQUIRED_SKILLS)
    def test_skill_has_yaml_frontmatter(self, skill_name):
        """Each SKILL.md must have YAML frontmatter with --- delimiters."""
        content = _read_skill(skill_name)
        assert content.startswith("---"), f"{skill_name}: missing opening ---"
        assert "---" in content[3:], f"{skill_name}: missing closing ---"

    @pytest.mark.parametrize("skill_name", REQUIRED_SKILLS)
    def test_skill_name_matches_directory(self, skill_name):
        """The 'name' field in frontmatter must match the directory name."""
        content = _read_skill(skill_name)
        # Extract frontmatter between --- markers
        parts = content.split("---", 2)
        assert len(parts) >= 3, f"{skill_name}: malformed frontmatter"
        frontmatter = parts[1]
        assert f"name: {skill_name}" in frontmatter, (
            f"{skill_name}: name field does not match directory name"
        )


class TestSkillContent:
    def test_test_scenario_design_skill(self):
        """test-scenario-design must cover Unit and System test scenarios."""
        content = _read_skill("test-scenario-design")
        assert "Unit Test Scenarios" in content
        assert "System Test Scenarios" in content

    def test_playwright_api_testing_skill(self):
        """playwright-api-testing must reference request fixture and test.step."""
        content = _read_skill("playwright-api-testing")
        assert "request fixture" in content.lower() or "request" in content
        assert "test.step" in content

    def test_api_test_quality_skill(self):
        """api-test-quality must reference compute_coverage and Final Report Template."""
        content = _read_skill("api-test-quality")
        assert "compute_coverage" in content
        assert "Final Report Template" in content


class TestSkillDescriptions:
    @pytest.mark.parametrize("skill_name", REQUIRED_SKILLS)
    def test_all_skills_have_description(self, skill_name):
        """Each SKILL.md frontmatter must have a non-empty description."""
        content = _read_skill(skill_name)
        parts = content.split("---", 2)
        frontmatter = parts[1]
        assert "description:" in frontmatter, f"{skill_name}: missing description"
        # Extract description value
        for line in frontmatter.strip().split("\n"):
            if line.strip().startswith("description:"):
                desc_value = line.split("description:", 1)[1].strip()
                assert len(desc_value) > 10, f"{skill_name}: description too short"
                break
