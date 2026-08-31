"""Smoke tests for SKILL.md files - verify structure and content.

The skills directory is user-maintained (2026-08): skills are discovered at
runtime via SkillsMiddleware with directory-name fallback, so these tests
validate structure generically rather than a fixed historical skill list.
"""
import pytest
from pathlib import Path

SKILLS_DIR = Path("src/app/skills")
# Core skills the platform expects to ship with.
EXPECTED_SKILLS = ["testcase-workflow", "large-system-testing", "unity-ui-test"]


def _actual_skills() -> list[str]:
    if not SKILLS_DIR.is_dir():
        return []
    return sorted(d.name for d in SKILLS_DIR.iterdir() if d.is_dir())


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_directory_exists(skill_name):
    assert (SKILLS_DIR / skill_name).is_dir(), f"Skill directory missing: {skill_name}"


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_md_exists(skill_name):
    assert (SKILLS_DIR / skill_name / "SKILL.md").is_file(), f"SKILL.md missing for: {skill_name}"


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_has_content_sections(skill_name):
    content = (SKILLS_DIR / skill_name / "SKILL.md").read_text(encoding="utf-8")
    assert len(content) > 500, f"SKILL.md for {skill_name} has insufficient content ({len(content)} chars)"
    assert "## " in content or "# " in content, f"SKILL.md for {skill_name} missing headers"


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_frontmatter_parseable_if_present(skill_name):
    """Frontmatter is optional (dir-name fallback); if present it must parse as YAML."""
    content = (SKILLS_DIR / skill_name / "SKILL.md").read_text(encoding="utf-8")
    if not content.startswith("---"):
        return
    parts = content.split("---", 2)
    assert len(parts) >= 3, f"SKILL.md for {skill_name} has unterminated frontmatter"
    import yaml
    frontmatter = yaml.safe_load(parts[1])
    assert frontmatter is None or isinstance(frontmatter, dict), (
        f"Invalid frontmatter for {skill_name}"
    )


def test_core_skills_present():
    actual = set(_actual_skills())
    for skill in EXPECTED_SKILLS:
        assert skill in actual, f"Missing skill directory: {skill}"


def test_testcase_workflow_has_stages():
    """testcase-workflow must describe the analyze -> design -> deliver flow."""
    content = (SKILLS_DIR / "testcase-workflow" / "SKILL.md").read_text(encoding="utf-8")
    assert "分析" in content, "Missing analysis stage"
    assert "设计" in content, "Missing design stage"
    assert "交付" in content, "Missing delivery stage"


def test_unity_ui_test_has_remoteserver():
    """unity-ui-test must document the LuaRemoteServer integration."""
    content = (SKILLS_DIR / "unity-ui-test" / "SKILL.md").read_text(encoding="utf-8")
    assert "LuaRemoteServer" in content or "16666" in content, "Missing LuaRemoteServer reference"
