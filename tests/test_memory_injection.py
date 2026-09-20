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
from langchain_core.messages import SystemMessage
from types import SimpleNamespace

import pytest

from src.app.middleware import memory_injection
from src.app.services import memory_service


@pytest.fixture
def memory_root(tmp_path: Path, monkeypatch) -> Path:
    """把记忆根目录指到临时目录（space 参数仍然按调用方给的值走）。

    要同时补**两处**：``memory_service.memory_root``（list_modules / ensure_seeded
    用它）和 ``memory_injection.memory_root``（中间件模块里是 ``from ... import
    memory_root`` 的模块级名字，改前者不会影响它）。
    """
    root = tmp_path / "memory"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(memory_service, "memory_root", lambda space_id="default": root)
    monkeypatch.setattr(memory_injection, "memory_root", lambda space_id="default": root)
    yield root


def _write(root: Path, name: str, body: str) -> None:
    (root / name).write_text(body, encoding="utf-8")


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
        _write(memory_root, "TOOLS.md", "# 环境速查\n\n- cbm exe: tools/codebase-memory/codebase-memory-mcp\n")
        ids = {m.file for m in memory_service.list_modules()}
        assert "TOOLS.md" in ids

    def test_create_and_delete_custom_module(self, memory_root: Path):
        module = memory_service.create_module("环境备忘", file="ENV.md", content="# ENV\n")
        assert (memory_root / "ENV.md").exists()
        assert memory_service.delete_module(module.id) is True
        assert not (memory_root / "ENV.md").exists()

    def test_legacy_profile_migration_is_idempotent(self, memory_root: Path):
        """旧 EverOS user.md 只搬一次。

        这里踩过：迁移的判据是"USER.md 还是种子内容"，而迁移是**追加**——
        种子文字永远还在，于是每次启动都再追加一份（实测涨到 161KB / 32 份）。
        现在以迁移标记为准。
        """
        legacy_dir = memory_root / "smart-test" / "default_project" / "users" / "platform"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "user.md").write_text(
            "用户偏好：结论先给答案，再给依据；输出一律中文；产物落工作区，"
            "不改动被测仓库；不确定的需求逐条列出来问，不要猜。\n", encoding="utf-8")
        for _ in range(3):
            memory_service.ensure_seeded()
        body = (memory_root / "USER.md").read_text(encoding="utf-8")
        assert body.count("从旧版记忆迁移（画像）") == 1
        assert body.count("用户偏好：结论先给答案") == 1

    def test_legacy_episodes_migration_is_idempotent(self, memory_root: Path):
        episode_dir = memory_root / "smart-test" / "default_project" / "users" / "platform" / "episodes"
        episode_dir.mkdir(parents=True)
        (episode_dir / "episode-2026-09-01.md").write_text(
            "### Subject\n跨天重置必须覆盖 04:59/05:00/05:01\n", encoding="utf-8")
        for _ in range(3):
            memory_service.ensure_seeded()
        body = (memory_root / "MEMORY.md").read_text(encoding="utf-8")
        assert body.count("从旧版记忆迁移（经历）") == 1
        assert body.count("04:59/05:00/05:01") == 1

    def test_builtin_module_cannot_be_deleted(self, memory_root: Path):
        memory_service.ensure_seeded()
        with pytest.raises(PermissionError):
            memory_service.delete_module("agents")


class TestToggle:
    def test_disabled_module_leaves_injection_sources(self, memory_root: Path):
        """停用某个模块 → 它不进注入来源，其它模块照旧。

        断言点在**官方路径**上（``enabled_memory_sources`` 就是喂给官方
        MemoryMiddleware 的 sources）：过去这条测的是平台自己那套
        ``build_context_block``，那套已经删掉（线上从来没有调用方）。
        """
        _write(memory_root, "MEMORY.md", "- 唯一一条值得记住的结论\n")
        assert any(src.endswith("MEMORY.md") for src in memory_injection.enabled_memory_sources())
        memory_service.set_enabled("memory", False)
        sources = memory_injection.enabled_memory_sources()
        assert not any(src.endswith("MEMORY.md") for src in sources)
        assert any(src.endswith("AGENTS.md") for src in sources)  # 别的模块不受影响


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
    """中间件按**官方生命周期**工作：before_agent 载入 → wrap_model_call 贴进 prompt。

    过去这几条测试直接在 wrap_model_call 里读文件（平台自己实现的老设计）；
    官方把"载入"和"贴进去"拆成两步，所以测试也要走两步。
    """

    @staticmethod
    def _load(middleware) -> dict:
        """跑一次 before_agent，拿到官方写进 state 的 memory_contents。"""
        update = asyncio.run(middleware.abefore_agent({}, None, {}))
        return dict(update or {})

    def test_appends_block_to_string_system_message(self, memory_root: Path,
                                                    mock_model_request):
        _write(memory_root, "MEMORY.md", "- 平台端口约定：LangGraph 5011\n")
        middleware = memory_injection.MemoryInjectionMiddleware()
        request = mock_model_request(
            messages=[], system_message=SystemMessage(content="你是测试专家。"),
            state=self._load(middleware))

        async def handler(req):
            return req.system_message.content

        result = asyncio.run(middleware.awrap_model_call(request, handler))
        # 官方 append_to_system_message 走 content_blocks，所以出参一定是块列表：
        # 原文一块 + 追加的一块。
        assert isinstance(result, list) and len(result) == 2
        assert result[0]["text"] == "你是测试专家。"
        assert "<agent_memory>" in result[1]["text"]
        assert "</agent_memory>" in result[1]["text"]
        assert "平台端口约定" in result[1]["text"]
        # 官方模板自带 memory_guidelines：明确教模型用 edit_file 把知识写回记忆。
        # 这是"模型知道自己可以更新记忆"的来源，不能丢。
        assert "<memory_guidelines>" in result[1]["text"]

    def test_appends_block_to_list_system_message(self, memory_root: Path,
                                                  mock_model_request):
        _write(memory_root, "MEMORY.md", "- 列表形态也要贴得上\n")
        middleware = memory_injection.MemoryInjectionMiddleware()
        request = mock_model_request(
            messages=[],
            system_message=SystemMessage(content=[{"type": "text", "text": "原文"}]),
            state=self._load(middleware))

        async def handler(req):
            return req.system_message.content

        result = asyncio.run(middleware.awrap_model_call(request, handler))
        assert isinstance(result, list) and len(result) == 2
        assert result[0]["text"] == "原文"
        assert "<agent_memory>" in result[1]["text"]

    def test_no_enabled_modules_reports_no_memory_loaded(self, memory_root: Path,
                                                         mock_model_request):
        """一个模块都没启用时，官方仍会贴模板，正文是 "(No memory loaded)"。

        这是官方语义而不是漏贴：模板里的 memory_guidelines 才是重点（教模型写回
        记忆）。要"完全不贴"得关总开关，见下一条。
        """
        for module in memory_service.list_modules():
            memory_service.set_enabled(module.id, False)
        middleware = memory_injection.MemoryInjectionMiddleware()
        assert memory_injection.enabled_memory_sources() == []
        request = mock_model_request(messages=[], system_message=SystemMessage(content="原文"),
                                     state=self._load(middleware))

        async def handler(req):
            return req.system_message.content

        result = asyncio.run(middleware.awrap_model_call(request, handler))
        assert isinstance(result, list) and len(result) == 2
        assert result[0]["text"] == "原文"
        assert "(No memory loaded)" in result[1]["text"]

    def test_global_switch_off_appends_nothing(self, memory_root: Path, monkeypatch,
                                              mock_model_request):
        """总开关关掉 → 来源为空 + system_prompt 为 None（官方此时完全不贴）。

        两件事都要成立：来源为空让 before_agent 不去读文件；system_prompt 为 None
        让 wrap_model_call 不贴模板。**过去这个开关实际无效**——它只被一个生产代码
        没人调用的函数读（那套手写拼装已随 2026-09-18 清理删除），于是设置页的
        「记忆总开关」关掉后，中间件照旧把记忆注入 system prompt。
        """
        _write(memory_root, "MEMORY.md", "- 这条不该出现\n")
        monkeypatch.setattr(memory_service.settings, "memory_enabled", False)
        middleware = memory_injection.MemoryInjectionMiddleware()
        assert memory_injection.enabled_memory_sources() == []
        assert middleware.system_prompt is None
        request = mock_model_request(messages=[], system_message=SystemMessage(content="原文"),
                                     state=self._load(middleware))

        async def handler(req):
            return req.system_message.content

        # system_prompt 为 None 时官方直接把原 system message 原样返回（内容不变，
        # 不是"贴一个空块"）。
        assert asyncio.run(middleware.awrap_model_call(request, handler)) == "原文"



class TestGlobalSwitchHotReload:
    """总闸要能"下一轮生效"（页面是这么写的）。

    机制：页面把 MEMORY_ENABLED 写进 .env → LangGraph 进程每次模型调用前
    ``refresh_from_env()`` 重读那几个键 → 中间件现读 ``settings.memory_enabled``。
    这条链路最容易断在两处，所以钉住：字段不在热更新名单里（静默要求重启），
    或者按字符串赋值（"false" 是真值，总闸永远关不掉）。
    """

    def test_memory_enabled_is_in_the_hot_reload_set(self):
        from src.app.agents.testcase import model_factory

        assert model_factory._ENV_REFRESH_KEYS.get("memory_enabled") == "MEMORY_ENABLED"
        assert "memory_enabled" in model_factory._BOOL_FIELDS

    def test_false_from_env_becomes_a_real_bool(self, tmp_path, monkeypatch):
        from src.app.agents.testcase import model_factory
        from src.app.core.config import settings

        env = tmp_path / ".env"
        env.write_text("MEMORY_ENABLED=false\n", encoding="utf-8")
        monkeypatch.setattr(model_factory, "_ENV_FILE", env)
        monkeypatch.setattr(model_factory, "_reload_state", {"mtime": -1, "sig": None})
        monkeypatch.setattr(settings, "memory_enabled", True)

        model_factory.refresh_from_env()

        assert settings.memory_enabled is False  # 不是字符串 "false"（那是真值）
