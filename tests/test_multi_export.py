"""Unit tests for multi-format export (EXPT-03: CSV/JSON/Markdown)."""
import json
import tempfile
from pathlib import Path
import pytest
from src.app.agents.testcase.tools import (
    export_test_cases,
    export_test_cases_to_excel,
    _export_csv,
    _export_json,
    _export_markdown,
)

# Get the raw function from the StructuredTool for direct testing
_export_test_cases = export_test_cases.func

SAMPLE_CASES = [
    {
        "id": "TC-PROJ-MOD-001",
        "title": "登录成功",
        "module": "登录模块",
        "type": "功能测试",
        "priority": "P0",
        "preconditions": ["用户已注册"],
        "steps": [
            {"action": "输入用户名", "expected": "显示用户名"},
            {"action": "点击登录", "expected": "跳转首页"},
        ],
        "test_data": {"username": "admin", "password": "Admin@123"},
        "expected_results": ["登录成功", "跳转到首页"],
        "remarks": "正常登录流程",
    },
    {
        "id": "TC-PROJ-MOD-002",
        "title": "密码错误",
        "module": "登录模块",
        "type": "异常测试",
        "priority": "P1",
        "preconditions": "用户已注册",
        "steps": [{"action": "输入错误密码", "expected": "提示密码错误"}],
        "test_data": "username: admin, password: wrong",
        "expected_results": "提示密码错误",
        "remarks": "",
    },
]


# --- CSV export tests ---


def test_csv_export_creates_file():
    """CSV export succeeds and file exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "test.csv"
        result = _export_csv(SAMPLE_CASES, str(output))
        assert Path(result).exists()
        assert result.endswith(".csv")


def test_csv_export_has_bom():
    """Per D-13: CSV file starts with UTF-8 BOM."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "test.csv"
        _export_csv(SAMPLE_CASES, str(output))
        with open(output, "rb") as f:
            bom = f.read(3)
        assert bom == b'\xef\xbb\xbf'


def test_csv_export_has_headers():
    """CSV first data line contains all 10 HEADERS."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "test.csv"
        _export_csv(SAMPLE_CASES, str(output))
        with open(output, "r", encoding="utf-8-sig") as f:
            first_line = f.readline()
        for header in ["用例编号", "用例标题", "所属模块", "用例类型", "优先级",
                       "前置条件", "测试步骤", "测试数据", "预期结果", "备注"]:
            assert header in first_line, f"Missing header: {header}"


def test_csv_export_has_data():
    """CSV file contains test case IDs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "test.csv"
        _export_csv(SAMPLE_CASES, str(output))
        content = output.read_text(encoding="utf-8-sig")
        assert "TC-PROJ-MOD-001" in content
        assert "TC-PROJ-MOD-002" in content


# --- JSON export tests ---


def test_json_export_creates_file():
    """JSON export succeeds and file exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "test.json"
        result = _export_json(SAMPLE_CASES, str(output))
        assert Path(result).exists()
        assert result.endswith(".json")


def test_json_export_has_xray_structure():
    """Per D-14: JSON has 'testCases' key (Jira Xray format)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "test.json"
        _export_json(SAMPLE_CASES, str(output))
        with open(output, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "testCases" in data
        assert isinstance(data["testCases"], list)
        assert len(data["testCases"]) == 2


def test_json_export_has_case_keys():
    """Each testCase has testCaseKey, summary, steps, status."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "test.json"
        _export_json(SAMPLE_CASES, str(output))
        with open(output, "r", encoding="utf-8") as f:
            data = json.load(f)
        for case in data["testCases"]:
            assert "testCaseKey" in case
            assert "summary" in case
            assert "steps" in case
            assert "status" in case
            assert case["status"] == "DRAFT"


# --- Markdown export tests ---


def test_markdown_export_creates_file():
    """Markdown export succeeds and file exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "test.md"
        result = _export_markdown(SAMPLE_CASES, str(output))
        assert Path(result).exists()
        assert result.endswith(".md")


def test_markdown_export_has_table():
    """Markdown file contains pipe characters and --- separators."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "test.md"
        _export_markdown(SAMPLE_CASES, str(output))
        content = output.read_text(encoding="utf-8")
        assert "|" in content
        assert "---" in content
        assert "TC-PROJ-MOD-001" in content


# --- Unified export dispatch tests ---


def test_unified_export_csv():
    """export_test_cases(format='csv') produces same output as _export_csv."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output1 = Path(tmpdir) / "direct.csv"
        output2 = Path(tmpdir) / "unified.csv"
        _export_csv(SAMPLE_CASES, str(output1))
        _export_test_cases(SAMPLE_CASES, str(output2), format="csv")
        assert output1.read_bytes() == output2.read_bytes()


def test_unified_export_unknown_format_raises():
    """Unknown format raises ValueError."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "test.xyz"
        with pytest.raises(ValueError, match="不支持的导出格式"):
            _export_test_cases(SAMPLE_CASES, str(output), format="xyz")


def test_unified_export_empty_cases_raises():
    """Empty test_cases list raises ValueError."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "test.csv"
        with pytest.raises(ValueError, match="测试用例列表为空"):
            _export_test_cases([], str(output), format="csv")
