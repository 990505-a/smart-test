"""记忆模块测试（harness 风格 Markdown 记忆 + 注入中间件）。

记忆 = 工作区 ``memory/`` 下的一组可开关 Markdown 文件。测试覆盖：
* 种子落盘与清单（幂等、自定义模块自动发现）
* 启用/停用对注入块的影响
* 追加条目 / 关键词检索
* 中间件把块贴到 system prompt 上
* 全局开关 memory_enabled
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.app.middleware import memory_injection
from src.app.services import memory_service


@pytest.fixture
def memory_root(tmp_path: Path, monkeypatch) -> Path:
    """把记忆根目录指到临时目录（space 参数仍然按调用方给的值走）。"""
    root = tmp_path / "memory"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(memory_service, "memory_root", lambda space_id="default": root)
    memory_service.invalidate_cache()
    yield root
    memory_service.invalidate_cache()


def _write(root: Path, name: str, body: str) -> None:
    (root / name).write_text(body, encoding="utf-8")
    memory_service.invalidate_cache()


class TestSeedAndManifest:
    def test_seeds_builtin_modules(self, memory_root: Path):
        modules = memory_service.list_modules()
        files = {m.file for m in modules}
        assert {"AGENTS.md", "MEMORY.md", "USER.md", "failures.md"} <= files
        for module in modules:
            if module.builtin:
                assert (memory_root / module.file).exists()

    def test_reseeding_is_idempotent_and_keeps_edits(self, memory_root: Path):
        _write(memory_root, "MEMORY.md", "# 我的记忆\n\n- 改动不应被覆盖\n")
        memory_service.ensure_seeded()
        assert "改动不应被覆盖" in (memory_root / "MEMORY.md").read_text(encoding="utf-8")

    def test_extra_markdown_becomes_module(self, memory_root: Path):
        memory_service.ensure_seeded()
        _write(memory_root, "TOOLS.md", "# 环境速查\n\n- cbm exe: C:/codebase/cbm-gs.exe\n")
        ids = {m.file for m in memory_service.list_modules()}
        assert "TOOLS.md" in ids

    def test_create_and_delete_custom_module(self, memory_root: Path):
        module = memory_service.create_module("环境备忘", file="ENV.md", content="# ENV\n")
        assert (memory_root / "ENV.md").exists()
        assert memory_service.delete_module(module.id) is True
        assert not (memory_root / "ENV.md").exists()

    def test_builtin_module_cannot_be_deleted(self, memory_root: Path):
        memory_service.ensure_seeded()
        with pytest.raises(PermissionError):
            memory_service.delete_module("agents")


class TestToggle:
    def test_disabled_module_leaves_context_block(self, memory_root: Path):
        _write(memory_root, "MEMORY.md", "- 唯一一条值得记住的结论\n")
        assert "唯一一条值得记住的结论" in memory_service.build_context_block()
        memory_service.set_enabled("memory", False)
        assert "唯一一条值得记住的结论" not in memory_service.build_context_block()

    def test_agents_md_is_injected_as_instruction(self, memory_root: Path):
        _write(memory_root, "AGENTS.md", "- 禁止编造产品规则\n")
        block = memory_service.build_context_block()
        assert "工作区指令" in block and "禁止编造产品规则" in block


class TestWriteAndSearch:
    def test_append_entry_adds_dated_bullet(self, memory_root: Path):
        memory_service.append_entry("memory", "周一 05:00 是跨天重置临界点", category="领域知识")
        body = (memory_root / "MEMORY.md").read_text(encoding="utf-8")
        assert "周一 05:00 是跨天重置临界点" in body
        assert "领域知识" in body

    def test_search_finds_line_with_location(self, memory_root: Path):
        _write(memory_root, "failures.md", "# failures\n\n- 别用 sleep 等加载：不稳定\n")
        _write(memory_root, "MEMORY.md", "# memory\n\n- 跨天重置覆盖 04:59/05:00/05:01\n")
        hits = memory_service.search("跨天重置")
        assert hits and hits[0].file == "MEMORY.md"
        assert hits[0].line >= 1
        assert memory_service.search("sleep 等加载")[0].file == "failures.md"

    def test_search_skips_disabled_modules(self, memory_root: Path):
        _write(memory_root, "MEMORY.md", "- 只在启用的模块里检索这个关键词\n")
        memory_service.set_enabled("memory", False)
        assert memory_service.search("这个关键词") == []


class TestInjectionMiddleware:
    def test_appends_block_to_string_system_message(self, memory_root: Path,
                                                    mock_model_request):
        _write(memory_root, "MEMORY.md", "- 平台端口约定：LangGraph 5011\n")
        middleware = memory_injection.MemoryInjectionMiddleware()
        request = mock_model_request(
            messages=[], system_message=SimpleNamespace(content="你是测试专家。"))

        async def handler(req):
            return req.system_message.content

        result = asyncio.run(middleware.awrap_model_call(request, handler))
        assert result.startswith("你是测试专家。")
        assert "<agent_memories>" in result
        assert "平台端口约定" in result
        assert result.rstrip().endswith("</agent_memories>")

    def test_appends_block_to_list_system_message(self, memory_root: Path,
                                                  mock_model_request):
        _write(memory_root, "MEMORY.md", "- 列表形态也要贴得上\n")
        middleware = memory_injection.MemoryInjectionMiddleware()
        request = mock_model_request(
            messages=[], system_message=SimpleNamespace(content=[{"type": "text", "text": "原文"}]))

        async def handler(req):
            return req.system_message.content

        result = asyncio.run(middleware.awrap_model_call(request, handler))
        assert isinstance(result, list) and len(result) == 2
        assert "<agent_memories>" in result[1]["text"]

    def test_no_memories_leaves_prompt_untouched(self, memory_root: Path,
                                                 mock_model_request):
        for module in memory_service.list_modules():
            memory_service.set_enabled(module.id, False)
        memory_service.invalidate_cache()
        middleware = memory_injection.MemoryInjectionMiddleware()
        request = mock_model_request(messages=[], system_message=SimpleNamespace(content="原文"))

        async def handler(req):
            return req.system_message.content

        assert asyncio.run(middleware.awrap_model_call(request, handler)) == "原文"

    def test_global_switch_off(self, memory_root: Path, monkeypatch):
        _write(memory_root, "MEMORY.md", "- 这条不该出现\n")
        monkeypatch.setattr(memory_service.settings, "memory_enabled", False)
        memory_service.invalidate_cache()
        assert memory_service.build_context_block() == ""

    def test_cache_invalidated_on_write(self, memory_root: Path):
        _write(memory_root, "MEMORY.md", "- 第一版\n")
        assert "第一版" in memory_service.build_context_block()
        _write(memory_root, "MEMORY.md", "- 第二版\n")
        block = memory_service.build_context_block()
        assert "第二版" in block and "第一版" not in block
