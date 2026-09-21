"""codebase-memory 的自管安装（services/cbm_install + 就绪中心的联动）。

安装本身要下载 40MB，测试里不碰网络：这里锁的是**判断逻辑**——装在哪、什么版本、
要不要升级、以及"装好了但 .env 指着别处"这个最容易白折腾半小时的状态。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.app.core import integrations
from src.app.core.config import settings
from src.app.services import cbm_install


def test_asset_tag_matches_this_platform():
    tag = cbm_install.asset_tag()
    assert tag.split("-")[0] in ("darwin", "linux", "windows")
    assert tag.split("-")[1] in ("amd64", "arm64")


def test_installed_version_reads_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(cbm_install, "CBM_MANAGED_DIR", tmp_path)
    assert cbm_install.installed_version() is None
    (tmp_path / ".installed.json").write_text(
        json.dumps({"version": "v0.11.0"}), "utf-8")
    assert cbm_install.installed_version() == "v0.11.0"
    (tmp_path / ".installed.json").write_text("{ 坏 JSON", "utf-8")
    assert cbm_install.installed_version() is None  # 坏文件不该炸


def test_managed_exe_follows_settings(monkeypatch):
    monkeypatch.setattr(settings, "codebase_memory_exe", "/custom/cbm")
    # 按 Path 比较：Windows 下 str() 给反斜杠，写死 POSIX 分隔符的断言跨不了平台
    assert cbm_install.managed_exe() == Path("/custom/cbm")


def test_binary_version_is_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "codebase_memory_exe", str(tmp_path / "nope"))
    assert cbm_install.binary_version() is None


def test_stale_exe_override_is_reported(monkeypatch, tmp_path):
    """平台装好了新版、但 CODEBASE_MEMORY_EXE 还指着不存在的旧路径时，
    就绪中心必须点名这件事——否则用户会一直以为"装了怎么还是不能用"。"""
    async def _fake_status():
        return {"available": False, "exe_present": False, "exe": "C:/codebase/cbm-gs.exe",
                "error": "CLI 启动失败: No such file or directory",
                "projects": [],
                "install": {"installed_version": "v0.11.0",
                            "managed_dir": str(tmp_path),
                            "configured_exe": "C:/codebase/cbm-gs.exe",
                            "using_managed": False}}

    from src.app.services import codebase_service

    monkeypatch.setattr(codebase_service, "status", _fake_status)
    import asyncio

    result = asyncio.run(integrations.probe("codebase-memory"))
    assert result["ready"] is False
    assert "已装在" in result["error"]
    assert "CODEBASE_MEMORY_EXE" in result["error"]
    assert "C:/codebase/cbm-gs.exe" in result["error"]


def test_checksum_parsing_rejects_unknown_asset(monkeypatch):
    class _Resp:
        text = "abc123  codebase-memory-mcp-darwin-arm64.tar.gz\n"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(cbm_install.httpx, "get", lambda *a, **k: _Resp())
    assert cbm_install._expected_sha("v0.11.0", "codebase-memory-mcp-darwin-arm64.tar.gz") == "abc123"
    with pytest.raises(cbm_install.InstallError):
        cbm_install._expected_sha("v0.11.0", "codebase-memory-mcp-freebsd-arm64.tar.gz")
