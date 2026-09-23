"""cbm_cli 的调用契约（services/codebase_service 的 CLI 路径）。

这些断言对着官方 codebase-memory v0.11.0 的实测行为写：

* 参数走 stdin（位置参数 JSON 自 v0.11.0 起 deprecated，会往 stderr 打警告）；
* 读工具默认输出**给人看的紧凑树**，要结构化 JSON 必须 format=json；写工具
  （index_repository / delete_project）默认就是 JSON 且不接受该参数。

用一个假的 exe（把 stdin 原样回显成 JSON）来验证管路，不需要真的装 40MB 二进制。
"""

from __future__ import annotations

import json
import stat
import sys

import pytest

from src.app.core.config import settings
from src.app.services import codebase_service


@pytest.fixture
def fake_exe(tmp_path, monkeypatch):
    """写一个假 exe：把 stdin 的 JSON 原样打回 stdout，另往 stderr 写一行日志。

    Windows 没有 POSIX 的可执行位/shebang，Popen 拉不起无扩展名的脚本——
    用 .cmd 垫片转调 python（生产是真正的 .exe，不受 fixture 影响）。
    """
    exe = _fake_executable(
        tmp_path, monkeypatch,
        "import json, sys\n"
        "raw = sys.stdin.read()\n"
        "sys.stderr.write('indexing: 42 files\\n')\n"
        "sys.stdout.write(json.dumps({'echo': json.loads(raw)}, ensure_ascii=False))\n",
    )
    return exe


def _fake_executable(tmp_path, monkeypatch, body: str) -> str:
    """写一个假 exe（python 脚本）+ 让 settings.codebase_memory_exe 指向它。

    POSIX：脚本加执行位直接 Popen；Windows：Popen 起不了脚本，写 .cmd 垫片
    （调 sys.executable 跑脚本），返回垫片路径。
    """
    script = tmp_path / "fake-cbm.py"
    script.write_text(body, "utf-8")
    if sys.platform == "win32":
        launcher = tmp_path / "fake-cbm.cmd"
        launcher.write_text(
            f'@echo off\r\n"{sys.executable}" "{script.as_posix()}"\r\n', "utf-8")
        exe = str(launcher)
    else:
        script.chmod(script.stat().st_mode | stat.S_IXUSR)
        exe = str(script)
    monkeypatch.setattr(settings, "codebase_memory_exe", exe)
    return exe


def test_cbm_args_injects_json_format_for_read_tools():
    for tool in ("list_projects", "search_graph", "query_graph", "index_status",
                 "search_code", "trace_path", "get_code_snippet", "get_architecture"):
        assert codebase_service.cbm_args(tool, {})["format"] == "json", tool


def test_cbm_args_leaves_write_tools_and_caller_values_alone():
    # 写工具不接受 format，注进去会直接报错
    assert "format" not in codebase_service.cbm_args("index_repository", {"repo_path": "x"})
    assert "format" not in codebase_service.cbm_args("delete_project", {"project": "p"})
    # 调用方显式给的值不被覆盖
    assert codebase_service.cbm_args("search_graph", {"format": "tree"})["format"] == "tree"


def test_cbm_cli_sync_sends_args_on_stdin(fake_exe):
    logs: list[str] = []
    result = codebase_service.cbm_cli_sync(
        "search_graph", {"project": "p", "name_pattern": "greet"}, timeout=30,
        on_log=logs.append)
    assert result["success"] is True
    # 回显 = exe 真的从 stdin 收到了这些参数，且 format 被注入
    assert result["data"]["echo"] == {"project": "p", "name_pattern": "greet",
                                      "format": "json"}
    assert any("indexing" in line for line in logs)  # stderr 回调照旧


def test_cbm_cli_sync_write_tool_args_pass_through(fake_exe):
    result = codebase_service.cbm_cli_sync("index_repository", {"repo_path": "/r", "mode": "fast"},
                                           timeout=30)
    assert result["data"]["echo"] == {"repo_path": "/r", "mode": "fast"}


def test_cbm_cli_sync_flags_non_json_output(tmp_path, monkeypatch):
    """读工具漏了 format=json 时 exe 回紧凑树——错误里必须点名是哪个工具，
    否则现场只看到一句"输出不是 JSON"，不知道该改哪。"""
    _fake_executable(
        tmp_path, monkeypatch,
        "import sys\nsys.stdin.read()\n"
        "print('projects: 0  (cols: name root_path)')\n",
    )

    result = codebase_service.cbm_cli_sync("list_projects", {}, timeout=30)
    assert result["success"] is False
    assert "list_projects" in result["error"]
    assert "不是 JSON" in result["error"]


def test_cbm_cli_sync_missing_exe_is_an_error_not_a_crash(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "codebase_memory_exe", str(tmp_path / "nope"))
    result = codebase_service.cbm_cli_sync("list_projects", {}, timeout=10)
    assert result["success"] is False
    assert result["error"]


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS 的 /tmp 软链才需要")
def test_project_name_matches_real_exe_darwin_vector():
    """实测向量（v0.11.0）：/private/tmp/cbm-test/demo-svc → private-tmp-cbm-test-demo-svc。"""
    assert codebase_service.project_name("/tmp/cbm-test/demo-svc") == \
        "private-tmp-cbm-test-demo-svc"
    assert json.dumps({"n": codebase_service.project_name("/tmp/a b")})  # 不抛异常即可
