"""Tests for RepoProxyBackend (per-run /repo/ mount)."""

import asyncio
import subprocess
import sys
import time
from pathlib import Path

import pytest
from langchain_core.runnables.config import set_config_context

from src.app.agents.testcase import repo_backend as rb
from src.app.agents.testcase.repo_backend import RepoProxyBackend


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    (tmp_path / "Scripts").mkdir()
    (tmp_path / "Scripts" / "reward.lua").write_text(
        "-- M72-177558\nlocal RewardConfig = { long_interval = 86400 }\nreturn RewardConfig\n",
        encoding="utf-8",
    )
    (tmp_path / "readme.md").write_text("hello needle world", encoding="utf-8")
    return tmp_path


def _run_mounted(repo_path: str, func, /, *args, **kwargs):
    """Run func with configurable.repo_path visible to langgraph.get_config().

    set_config_context sets the contextvar inside a *copied* context and
    yields it — code under test must run via ctx.run (mirrors how LangGraph
    executes tools inside the runnable context).
    """
    with set_config_context({"configurable": {"repo_path": repo_path}}) as ctx:
        return ctx.run(func, *args, **kwargs)


def test_not_mounted_returns_error(repo: Path):
    backend = RepoProxyBackend()
    ls = backend.ls("/")
    assert ls.error and "未挂载" in ls.error
    read = backend.read("/Scripts/reward.lua")
    assert read.error and "未挂载" in read.error
    grep = backend.grep("RewardConfig")
    assert grep.error and "未挂载" in grep.error
    glob = backend.glob("*.lua")
    assert glob.error and "未挂载" in glob.error


def test_invalid_repo_path_returns_error(tmp_path: Path):
    backend = RepoProxyBackend()
    result = _run_mounted(str(tmp_path / "does-not-exist"), backend.ls, "/")
    assert result.error and "不存在" in result.error


def test_mounted_ls_read_grep_glob(repo: Path):
    backend = RepoProxyBackend()

    ls = _run_mounted(str(repo), backend.ls, "/")
    assert ls.error is None
    names = {e["path"].rstrip("/") for e in (ls.entries or [])}
    assert "/Scripts" in names and "/readme.md" in names

    read = _run_mounted(str(repo), backend.read, "/Scripts/reward.lua")
    assert read.error is None
    assert "RewardConfig" in (read.file_data or {}).get("content", "")

    grep = _run_mounted(str(repo), backend.grep, "RewardConfig", path="/")
    assert grep.error is None
    assert any("reward.lua" in m["path"] for m in (grep.matches or []))

    glob = _run_mounted(str(repo), backend.glob, "**/*.lua")
    assert glob.error is None
    assert any("reward.lua" in m["path"] for m in (glob.matches or []))


def test_mount_is_read_only(repo: Path):
    backend = RepoProxyBackend()
    write = _run_mounted(str(repo), backend.write, "/new_file.txt", "data")
    assert write.error and "只读" in write.error
    edit = _run_mounted(str(repo), backend.edit, "/readme.md", "hello", "bye")
    assert edit.error and "只读" in edit.error
    assert not (repo / "new_file.txt").exists()
    assert (repo / "readme.md").read_text(encoding="utf-8") == "hello needle world"


def test_path_traversal_blocked(repo: Path):
    backend = RepoProxyBackend()
    (repo.parent / "secret.txt").write_text("outside", encoding="utf-8")
    result = _run_mounted(str(repo), backend.read, "/../secret.txt")
    assert result.error is not None


def test_backend_cache_reuse(repo: Path):
    backend = RepoProxyBackend()
    _run_mounted(str(repo), backend.ls, "/")
    _run_mounted(str(repo), backend.ls, "/")
    assert str(repo) in backend._cache


# ---- dsh-style grep guards -------------------------------------------------


def test_grep_inline_cap_and_truncated(repo: Path):
    """250 inline matches (dsh GREP_MAX_MATCHES) + truncated=True on overflow."""
    (repo / "many.lua").write_text(
        "\n".join(f"needle_{i}" for i in range(300)) + "\n", encoding="utf-8"
    )
    backend = RepoProxyBackend()
    result = _run_mounted(str(repo), backend.grep, "needle_")
    assert result.error is None
    assert len(result.matches or []) == rb._RG_MAX_TOTAL
    assert result.truncated is True


def test_grep_line_preview_truncated(repo: Path):
    (repo / "long.lua").write_text("needle " + "x" * 5000 + "\n", encoding="utf-8")
    backend = RepoProxyBackend()
    result = _run_mounted(str(repo), backend.grep, "needle ")
    assert result.error is None
    # rg 多线程输出顺序不确定，按文件过滤而非依赖 matches[0]
    long_matches = [m for m in (result.matches or []) if "long.lua" in m["path"]]
    assert long_matches
    text = long_matches[0]["text"]
    assert text.endswith("…(行已截断)")
    assert len(text) <= rb._RG_LINE_CAP + 20


def test_grep_raw_output_overflow_fails_fast(repo: Path, monkeypatch):
    """>20MB raw stdout → structured error, not a slow death (dsh RAW_OUTPUT cap)."""
    monkeypatch.setattr(rb, "_RG_RAW_CAP", 200)
    (repo / "a.lua").write_text("needle" + "y" * 400 + "\n", encoding="utf-8")
    backend = RepoProxyBackend()
    result = _run_mounted(str(repo), backend.grep, "needle")
    assert result.error and "上限" in result.error


def test_kill_tree_terminates_process():
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    rb._kill_tree(proc)
    assert proc.poll() is not None


def test_agrep_happy_path(repo: Path):
    """agrep override keeps get_config() working through asyncio.to_thread."""
    backend = RepoProxyBackend()
    result = _run_mounted(
        str(repo), asyncio.run, backend.agrep("RewardConfig", path="/")
    )
    assert result.error is None
    assert any("reward.lua" in m["path"] for m in (result.matches or []))


def test_agrep_timeout_returns_error(repo: Path, monkeypatch):
    monkeypatch.setattr(rb, "_RG_ASYNC_BUDGET", 0.2)
    backend = RepoProxyBackend()

    def slow(*args, **kwargs):
        time.sleep(1.0)
        return rb.GrepResult(matches=[])

    backend._grep_with_cancel = slow  # type: ignore[method-assign]
    result = _run_mounted(
        str(repo), asyncio.run, backend.agrep("RewardConfig", path="/")
    )
    assert result.error and "超时" in result.error
