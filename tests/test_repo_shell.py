"""Tests for RepoAwareShellBackend (full_access 档 /repo/ shell 路径翻译)."""

from pathlib import Path

import pytest
from deepagents.backends import LocalShellBackend
from langchain_core.runnables.config import set_config_context

from src.app.agents.testcase.repo_backend import RepoAwareShellBackend


@pytest.fixture()
def backend(tmp_path: Path) -> RepoAwareShellBackend:
    return RepoAwareShellBackend(
        root_dir=tmp_path, virtual_mode=True, inherit_env=False, timeout=5
    )


@pytest.fixture()
def captured(monkeypatch):
    """Capture the command the parent LocalShellBackend would run."""
    box: dict = {}

    def fake_execute(self, command, *, timeout=None):  # noqa: ARG001
        box["command"] = command
        return object()

    monkeypatch.setattr(LocalShellBackend, "execute", fake_execute)
    return box


def _run(configurable: dict, func, /, *args, **kwargs):
    with set_config_context({"configurable": configurable}) as ctx:
        return ctx.run(func, *args, **kwargs)


def test_full_access_rewrites_path(backend, captured, tmp_path):
    _run(
        {"repo_path": str(tmp_path), "permission_mode": "full_access"},
        backend.execute,
        "git -C /repo log --oneline -5",
    )
    real = tmp_path.resolve().as_posix()
    assert captured["command"] == f"git -C {real} log --oneline -5"


def test_full_access_chained_and_nested(backend, captured, tmp_path):
    real = tmp_path.resolve().as_posix()
    _run(
        {"repo_path": str(tmp_path), "permission_mode": "full_access"},
        backend.execute,
        "cd /repo && git -C /repo log",
    )
    assert captured["command"] == f"cd {real} && git -C {real} log"

    _run(
        {"repo_path": str(tmp_path), "permission_mode": "full_access"},
        backend.execute,
        'cat "/repo/Scripts/reward.lua"',
    )
    assert captured["command"] == f'cat "{real}/Scripts/reward.lua"'


def test_similar_tokens_not_touched(backend, captured, tmp_path):
    cmd = "ls /repository /repo.txt repo"
    _run(
        {"repo_path": str(tmp_path), "permission_mode": "full_access"},
        backend.execute,
        cmd,
    )
    assert captured["command"] == cmd


@pytest.mark.parametrize("mode", ["workspace_write", "read_only", ""])
def test_other_modes_passthrough(backend, captured, tmp_path, mode):
    cmd = "git -C /repo log"
    _run({"repo_path": str(tmp_path), "permission_mode": mode}, backend.execute, cmd)
    assert captured["command"] == cmd


def test_legacy_execute_approval_off_rewrites(backend, captured, tmp_path):
    _run(
        {"repo_path": str(tmp_path), "execute_approval": "off"},
        backend.execute,
        "git -C /repo log",
    )
    real = tmp_path.resolve().as_posix()
    assert captured["command"] == f"git -C {real} log"


def test_no_repo_path_passthrough(backend, captured):
    cmd = "git -C /repo log"
    _run({"permission_mode": "full_access"}, backend.execute, cmd)
    assert captured["command"] == cmd


def test_outside_runnable_context_passthrough(backend, captured):
    # 无 LangGraph runnable 上下文：get_config() 抛 RuntimeError → 不翻译
    backend.execute("git -C /repo log")
    assert captured["command"] == "git -C /repo log"
