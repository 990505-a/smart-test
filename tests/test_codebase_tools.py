"""代码图谱智能体工具测试（agents/codebase/tools）。

重点在**项目绑定**：工具不再自己拼 slug，而是用 codebase_service.project_name
解析本次会话选中的仓库。过去这里和各处各写了一份等价实现，路径写法一变
（尾斜杠、反斜杠）就会静默查不到图谱。
"""

from __future__ import annotations

import json

import pytest

from src.app.agents import workspace_backend
from src.app.agents.codebase import tools
from src.app.services import codebase_service


def _mount(monkeypatch, value: str) -> None:
    monkeypatch.setattr(workspace_backend, "_run_configurable",
                        lambda: {"workspace_path": value})


@pytest.fixture
def captured(monkeypatch):
    """截获 cbm_call，记录工具真的把哪个 project 传下去了。"""
    calls: list[dict] = []

    async def _fake(tool_name, args, **kwargs):
        calls.append({"tool": tool_name, "args": args, **kwargs})
        return {"success": True, "data": {"ok": True}}

    monkeypatch.setattr(codebase_service, "cbm_call", _fake)
    return calls


class TestProjectBinding:
    def test_uses_shared_project_name(self, monkeypatch):
        # 唯一实现：工具不自己拼 slug，一律问 codebase_service（realpath + 官方
        # 归一化规则）。这里只断言"两边一致"，规则本身在 test_codebase_service。
        _mount(monkeypatch, "/Users/you/proj")
        assert tools._project() == codebase_service.project_name("/Users/you/proj")

    def test_unix_path_matches_shared_rule(self, monkeypatch):
        _mount(monkeypatch, "/Users/you/proj")
        assert tools._project() == codebase_service.project_name("/Users/you/proj")

    def test_no_mount_is_empty(self, monkeypatch):
        monkeypatch.setattr(workspace_backend, "_run_configurable", lambda: {})
        assert tools._project() == ""


class TestToolsUseTheBoundProject:
    @pytest.mark.asyncio
    async def test_graph_search_passes_project(self, monkeypatch, captured):
        _mount(monkeypatch, "/Users/you/proj")
        out = await tools.graph_search.ainvoke({"query": "login", "limit": 5})
        assert captured[-1]["tool"] == "search_graph"
        assert captured[-1]["args"]["project"] == codebase_service.project_name("/Users/you/proj")
        assert captured[-1]["args"]["name_pattern"] == "login"
        # 读工具必须带 format=json：官方 v0.11.0 默认回紧凑树，平台要结构化 JSON
        assert captured[-1]["args"]["format"] == "json"
        assert json.loads(out) == {"ok": True}

    @pytest.mark.asyncio
    async def test_graph_search_semantic_splits_keywords(self, monkeypatch, captured):
        _mount(monkeypatch, "/repo")
        await tools.graph_search.ainvoke({"query": "登录, 协议 校验", "semantic": True})
        args = captured[-1]["args"]
        assert args["semantic_query"] == ["登录", "协议", "校验"]

    @pytest.mark.asyncio
    async def test_trace_symbol_clamps_depth(self, monkeypatch, captured):
        _mount(monkeypatch, "/repo")
        await tools.trace_symbol.ainvoke({"function_name": "start", "depth": 99})
        assert captured[-1]["args"]["depth"] == 3
        await tools.trace_symbol.ainvoke({"function_name": "start", "depth": 0})
        assert captured[-1]["args"]["depth"] == 1

    @pytest.mark.asyncio
    async def test_trace_symbol_normalizes_direction(self, monkeypatch, captured):
        _mount(monkeypatch, "/repo")
        await tools.trace_symbol.ainvoke({"function_name": "start", "direction": "sideways"})
        assert captured[-1]["args"]["direction"] == "both"

    @pytest.mark.asyncio
    async def test_read_symbol_uses_qualified_name(self, monkeypatch, captured):
        _mount(monkeypatch, "/repo")
        await tools.read_symbol.ainvoke({"qualified_name": "a.b.c"})
        assert captured[-1]["tool"] == "get_code_snippet"
        assert captured[-1]["args"]["qualified_name"] == "a.b.c"


class TestDegradedPath:
    """未选中仓库时不打图谱，直接给可执行的降级建议（别让模型反复重试）。"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tool_call", [
        ("graph_search", {"query": "x"}),
        ("read_symbol", {"qualified_name": "a.b"}),
        ("repo_architecture", {}),
        ("trace_symbol", {"function_name": "start"}),
    ])
    async def test_no_mount_returns_hint_without_calling_graph(
            self, monkeypatch, captured, tool_call):
        monkeypatch.setattr(workspace_backend, "_run_configurable", lambda: {})
        name, args = tool_call
        out = await getattr(tools, name).ainvoke(args)
        assert out.startswith("Error:")
        assert "grep" in out and "代码图谱" in out
        assert captured == []  # 没挂仓库就不该发起图谱调用

    @pytest.mark.asyncio
    async def test_graph_error_includes_original_reason(self, monkeypatch):
        _mount(monkeypatch, "/repo")

        async def _fail(tool_name, args, **kwargs):
            return {"success": False, "error": "exe 不可达"}

        monkeypatch.setattr(codebase_service, "cbm_call", _fail)
        out = await tools.graph_search.ainvoke({"query": "x"})
        assert "exe 不可达" in out
