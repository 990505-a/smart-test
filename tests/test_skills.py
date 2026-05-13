"""Smoke tests for SKILL.md files - verify frontmatter and content."""
import pytest
from pathlib import Path
import yaml

SKILLS_DIR = Path("src/app/skills")
EXPECTED_SKILLS = ["requirement-analysis", "test-strategy", "test-case-design", "quality-review", "output-formatter", "test-data-generator"]


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_directory_exists(skill_name):
    assert (SKILLS_DIR / skill_name).is_dir(), f"Skill directory missing: {skill_name}"


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_md_exists(skill_name):
    assert (SKILLS_DIR / skill_name / "SKILL.md").is_file(), f"SKILL.md missing for: {skill_name}"


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_frontmatter_valid(skill_name):
    content = (SKILLS_DIR / skill_name / "SKILL.md").read_text(encoding="utf-8")
    # Parse YAML between --- delimiters
    parts = content.split("---", 2)
    assert len(parts) >= 3, f"SKILL.md for {skill_name} missing YAML frontmatter delimiters"
    frontmatter = yaml.safe_load(parts[1])
    assert isinstance(frontmatter, dict), f"Invalid frontmatter for {skill_name}"
    assert "name" in frontmatter, f"Missing 'name' in frontmatter for {skill_name}"
    assert frontmatter["name"] == skill_name, f"Name mismatch: expected '{skill_name}', got '{frontmatter['name']}'"
    assert "description" in frontmatter, f"Missing 'description' in frontmatter for {skill_name}"
    assert len(frontmatter["description"]) > 20, f"Description too short for {skill_name}"


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_has_content_sections(skill_name):
    content = (SKILLS_DIR / skill_name / "SKILL.md").read_text(encoding="utf-8")
    assert len(content) > 500, f"SKILL.md for {skill_name} has insufficient content ({len(content)} chars)"
    assert "## " in content, f"SKILL.md for {skill_name} missing section headers"


def test_all_expected_skills_present():
    actual_dirs = {d.name for d in SKILLS_DIR.iterdir() if d.is_dir()}
    for skill in EXPECTED_SKILLS:
        assert skill in actual_dirs, f"Missing skill directory: {skill}"


def test_requirement_analysis_has_ppdcs():
    """D-04: requirement-analysis must include PPDCS five-dimension analysis."""
    content = (SKILLS_DIR / "requirement-analysis" / "SKILL.md").read_text(encoding="utf-8")
    assert "PPDCS" in content, "Missing PPDCS reference in requirement-analysis"
    assert "Process" in content, "Missing Process dimension in PPDCS"
    assert "Product" in content, "Missing Product dimension in PPDCS"
    assert "Data" in content, "Missing Data dimension in PPDCS"
    assert "Configuration" in content, "Missing Configuration dimension in PPDCS"
    assert "Structure" in content, "Missing Structure dimension in PPDCS"


def test_test_strategy_has_kufi():
    """D-04: test-strategy must include KUFI classification."""
    content = (SKILLS_DIR / "test-strategy" / "SKILL.md").read_text(encoding="utf-8")
    assert "KUFI" in content, "Missing KUFI reference in test-strategy"
    assert "Know" in content, "Missing Know category in KUFI"
    assert "Understand" in content, "Missing Understand category in KUFI"
    assert "Familiar" in content, "Missing Familiar category in KUFI"
    assert "Infer" in content, "Missing Infer category in KUFI"


def test_quality_review_has_coverage():
    """D-04: quality-review must include coverage evaluation."""
    content = (SKILLS_DIR / "quality-review" / "SKILL.md").read_text(encoding="utf-8")
    assert "功能覆盖率" in content or "Functional Coverage" in content, "Missing functional coverage in quality-review"
    assert "风险覆盖率" in content or "Risk Coverage" in content, "Missing risk coverage in quality-review"
    assert "30" in content, "Missing completeness weight (30%)"
    assert "25" in content, "Missing accuracy weight (25%)"


def test_output_formatter_has_tc_convention():
    """D-10: output-formatter must define TC numbering convention."""
    content = (SKILLS_DIR / "output-formatter" / "SKILL.md").read_text(encoding="utf-8")
    assert "TC-[PROJECT]-[MODULE]-[NNN]" in content or "TC-XXX" in content or "TC-[" in content, "Missing TC numbering convention"
    assert "Excel" in content, "Missing Excel format reference"
