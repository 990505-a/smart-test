"""Unit tests for the /api/v2/files workspace file endpoint.

安全契约：只服务 workspace 根目录内的文件；越界（绝对路径指向外部、``..``
穿越、指向外部的符号链接）一律 404，不区分"不存在"与"不许读"。
"""
from __future__ import annotations

import pytest

from src.app.api.v2 import files as files_api


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    ws = tmp_path / "workspace"
    (ws / "default" / "agent").mkdir(parents=True)
    qr = ws / "default" / "agent" / "qr.png"
    qr.write_bytes(b"\x89PNG fake")
    outside = tmp_path / "secret.txt"
    outside.write_text("top secret")
    monkeypatch.setattr(files_api.settings, "workspace_dir", ws)
    return {"root": ws, "qr": qr, "outside": outside}


def _resolve(raw: str):
    return files_api._resolve_inside_workspace(raw)


def test_absolute_path_inside_workspace(workspace):
    assert _resolve(str(workspace["qr"])) == workspace["qr"].resolve()


def test_relative_to_workspace_root(workspace):
    assert _resolve("default/agent/qr.png") == workspace["qr"].resolve()


def test_repo_relative_form_with_workspace_prefix(workspace):
    # 智能体最爱写的形态：workspace/default/...（相对仓库根）
    assert _resolve("workspace/default/agent/qr.png") == workspace["qr"].resolve()


def test_traversal_outside_rejected(workspace):
    assert _resolve(str(workspace["root"] / ".." / "secret.txt")) is None
    assert _resolve("../../etc/passwd") is None


def test_absolute_path_outside_rejected(workspace):
    assert _resolve(str(workspace["outside"])) is None


def test_symlink_pointing_outside_rejected(workspace):
    link = workspace["root"] / "default" / "leak.txt"
    try:
        link.symlink_to(workspace["outside"])
    except OSError:
        pytest.skip("当前环境无法创建符号链接（Windows 需开发者模式/管理员）")
    assert _resolve(str(link)) is None


def test_malformed_paths_return_none(workspace):
    for raw in ("", "   ", "NUL\x00path"):
        assert _resolve(raw) is None


@pytest.mark.asyncio
async def test_endpoint_serves_file_and_404(workspace):
    resp = await files_api.read_workspace_file(path=str(workspace["qr"]))
    assert resp.media_type == "image/png"

    with pytest.raises(files_api.HTTPException) as exc:
        await files_api.read_workspace_file(path=str(workspace["outside"]))
    assert exc.value.status_code == 404
