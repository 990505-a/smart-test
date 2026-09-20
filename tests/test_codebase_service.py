"""Codebase-graph module tests.

Covers the pure logic of the .cbmignore managed-block writer (file-type
rules) and the project-name derivation shared by the service layer.
"""

from __future__ import annotations

from pathlib import Path

from src.app.services import codebase_service
from src.app.services.codebase_service import (
    normalize_extensions,
    project_name,
    write_cbmignore_block,
)


# ---------------------------------------------------------------- naming ----

def test_project_name_rule():
    """纯字符串规则（与平台无关的那半边）。

    末两个向量是对着官方 v0.11.0 的 `cli index_repository` 实测出来的：
    /private/tmp/cbm-test/demo-svc → private-tmp-cbm-test-demo-svc。
    """
    norm = codebase_service._normalize_project_path  # noqa: SLF001 — 被测的就是这条规则
    assert norm("E:/m72-publish/m72") == "E-m72-publish-m72"
    assert norm("D:/projects/my-app") == "D-projects-my-app"
    assert norm(r"E:\m72-publish\m72") == "E-m72-publish-m72"
    assert norm("/private/tmp/cbm-test/My_Repo.v2") == "private-tmp-cbm-test-My_Repo.v2"
    # 旧 GS 定制版的 replace("/", "-") 会留下前导 '-'，官方版不会——这条差别
    # 就是"换官方版后所有图谱查询失联"的根因，钉在这里防回归。
    assert not norm("/private/tmp/x").startswith("-")


def test_project_name_resolves_symlinks(tmp_path):
    """exe 先 realpath 再归一化：macOS 上 /tmp → /private/tmp 必须跟着走。"""
    import os

    link = tmp_path / "link"
    real = tmp_path / "real"
    real.mkdir()
    link.symlink_to(real)
    assert project_name(str(link)) == project_name(os.path.realpath(str(link)))


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
