"""工作区挂载测试（dsh 风格：cwd = 本次对话挂载的目录，真实路径语义）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.app.agents import workspace_backend
from src.app.agents.workspace_backend import WorkspaceShellBackend


@pytest.fixture
def backend(tmp_path: Path) -> WorkspaceShellBackend:
    default = tmp_path / "platform" / "testcase"
    default.mkdir(parents=True, exist_ok=True)
    return WorkspaceShellBackend(default)


def _mount(monkeypatch, value: str) -> None:
    monkeypatch.setattr(workspace_backend, "_run_configurable", lambda: {"workspace_path": value})


class TestWorkspaceResolution:
    def test_no_mount_falls_back_to_platform_dir(self, backend, tmp_path, monkeypatch):
        monkeypatch.setattr(workspace_backend, "_run_configurable", lambda: {})
        assert backend.cwd == (tmp_path / "platform" / "testcase").resolve()

    def test_mounted_dir_becomes_cwd(self, backend, tmp_path, monkeypatch):
        mounted = tmp_path / "my-project"
        mounted.mkdir()
        _mount(monkeypatch, str(mounted))
        assert backend.cwd == mounted.resolve()

    def test_legacy_repo_path_key_still_works(self, backend, tmp_path, monkeypatch):
        mounted = tmp_path / "legacy"
        mounted.mkdir()
        monkeypatch.setattr(workspace_backend, "_run_configurable",
                            lambda: {"repo_path": str(mounted)})
        assert backend.cwd == mounted.resolve()

    def test_missing_dir_falls_back(self, backend, tmp_path, monkeypatch):
        _mount(monkeypatch, str(tmp_path / "does-not-exist"))
        assert backend.cwd == (tmp_path / "platform" / "testcase").resolve()

    def test_outside_run_context_is_safe(self, backend):
        # 没有 langgraph config（裸调用 / 进程外）时不该抛异常，只返回空串
        assert isinstance(workspace_backend.mounted_workspace_path(), str)
        assert backend.cwd.exists()


class TestRealPathSemantics:
    def test_relative_paths_resolve_under_workspace(self, backend, tmp_path, monkeypatch):
        mounted = tmp_path / "ws"
        mounted.mkdir()
        _mount(monkeypatch, str(mounted))
        backend.write("notes.md", "hello")
        assert (mounted / "notes.md").read_text(encoding="utf-8") == "hello"
        assert backend.read("notes.md").file_data["content"] == "hello"

    def test_absolute_paths_outside_workspace_are_allowed(self, backend, tmp_path, monkeypatch):
        """完全权限的工作区模型：完全权限之外的位置也能读写（不是沙箱）。"""
        mounted = tmp_path / "ws"
        mounted.mkdir()
        outside = tmp_path / "outside.txt"
        _mount(monkeypatch, str(mounted))
        backend.write(str(outside), "outside-content")
        assert outside.read_text(encoding="utf-8") == "outside-content"
        assert backend.read(str(outside)).file_data["content"] == "outside-content"

    def test_glob_defaults_to_workspace(self, backend, tmp_path, monkeypatch):
        mounted = tmp_path / "ws"
        (mounted / "src").mkdir(parents=True)
        (mounted / "src" / "a.lua").write_text("-- a", encoding="utf-8")
        (tmp_path / "outside.lua").write_text("-- outside", encoding="utf-8")
        _mount(monkeypatch, str(mounted))
        matches = backend.glob("*.lua").matches or []
        assert any("a.lua" in (m.get("path") or "") for m in matches)
        assert not any("outside.lua" in (m.get("path") or "") for m in matches)

    def test_shell_runs_in_mounted_workspace(self, backend, tmp_path, monkeypatch):
        mounted = tmp_path / "ws"
        mounted.mkdir()
        _mount(monkeypatch, str(mounted))
        result = backend.execute("pwd")
        assert result.exit_code == 0
        assert str(mounted) in (result.output or "")

    def test_backend_advertises_shell(self, backend):
        """execute 工具是否暴露取决于 SandboxBackendProtocol 判定，不能因为包了一层就丢。"""
        from deepagents.backends.protocol import SandboxBackendProtocol

        assert isinstance(backend, SandboxBackendProtocol)
