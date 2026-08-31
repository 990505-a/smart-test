"""Codebase-graph module tests.

Covers the pure logic of the .cbmignore managed-block writer (file-type
rules) and the project-name derivation shared by the service layer.
"""

from __future__ import annotations

from pathlib import Path

from src.app.services.codebase_service import (
    normalize_extensions,
    project_name,
    write_cbmignore_block,
)


# ---------------------------------------------------------------- naming ----

def test_project_name_rule():
    assert project_name("E:/m72-publish/m72") == "E-m72-publish-m72"
    assert project_name("D:/projects/my-app") == "D-projects-my-app"


def test_normalize_extensions():
    assert normalize_extensions(["gs", ".LUA", "", ".cs", "cs"]) == [".gs", ".lua", ".cs"]
    assert normalize_extensions(None) == []
    assert normalize_extensions(["..bad", "a b"]) == []  # 非法形态被丢弃


# ---------------------------------------------------------- .cbmignore ----

def _read(repo: Path) -> str:
    return (repo / ".cbmignore").read_text(encoding="utf-8")


def test_include_block_written_and_user_content_preserved(tmp_path: Path):
    (tmp_path / ".cbmignore").write_text("# my own rules\nbuild/\n", encoding="utf-8")
    err = write_cbmignore_block(str(tmp_path), "include", [".gs", ".lua"])
    assert err is None
    content = _read(tmp_path)
    # 用户自有内容保留
    assert "# my own rules" in content and "build/" in content
    # gitignore 反选三件套：全排除 → 放行目录 → 放行扩展名
    assert "\n*\n" in content and "!*/" in content
    assert "!*.gs" in content and "!*.lua" in content


def test_managed_block_replaced_on_mode_change(tmp_path: Path):
    write_cbmignore_block(str(tmp_path), "include", [".gs"])
    write_cbmignore_block(str(tmp_path), "exclude", [".png"])
    content = _read(tmp_path)
    assert "!*.gs" not in content
    assert "*.png" in content
    assert content.count("BEGIN smart-test-platform") == 1


def test_all_mode_removes_managed_block(tmp_path: Path):
    (tmp_path / ".cbmignore").write_text("# user\nlogs/\n", encoding="utf-8")
    write_cbmignore_block(str(tmp_path), "exclude", [".png"])
    assert "BEGIN smart-test-platform" in _read(tmp_path)
    write_cbmignore_block(str(tmp_path), "all", [])
    content = _read(tmp_path)
    assert "BEGIN smart-test-platform" not in content
    assert "# user" in content and "logs/" in content and "*.png" not in content


def test_block_created_when_file_absent(tmp_path: Path):
    err = write_cbmignore_block(str(tmp_path), "include", [".gs"])
    assert err is None
    content = _read(tmp_path)
    assert content.count("BEGIN smart-test-platform") == 1
    assert "!*.gs" in content


def test_write_failure_returns_error(tmp_path: Path):
    # 传一个文件路径当仓库目录 → 写 .cbmignore 时失败
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    err = write_cbmignore_block(str(blocker), "include", [".gs"])
    assert isinstance(err, str) and "失败" in err
