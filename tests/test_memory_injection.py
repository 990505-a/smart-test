"""Unit tests for MemoryInjectionMiddleware (EverOS file-scan catalog + cache).

记忆目录从 EverOS 的 Markdown 记忆根目录扫描生成（不再查 DB）：
episodes/*.md 的 `### Subject` 行 → 「[日期] 主题」目录条目。
"""
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import SystemMessage

import src.app.middleware.memory_injection as memory_injection
from src.app.middleware.memory_injection import (
    MemoryInjectionMiddleware,
    build_memory_catalog,
    invalidate_memory_cache,
)
from tests.conftest import MockModelRequest

EPISODE_MD = """---
id: episode_log_tester_2026-08-31
type: episode_daily
user_id: platform
date: '2026-08-31'
entry_count: 2
---

<!-- entry:ep_1 -->
## ep_1

### Subject
第一条记忆主题行

### Summary
摘要内容

<!-- /entry:ep_1 -->
<!-- entry:ep_2 -->
## ep_2

### Subject
第二条记忆主题行

### Summary
摘要内容 2

<!-- /entry:ep_2 -->
"""


@pytest.fixture(autouse=True)
def _reset_cache():
    invalidate_memory_cache()
    yield
    invalidate_memory_cache()


@pytest.fixture
def memory_root(tmp_path, monkeypatch):
    """把 EverOS 记忆根目录指到临时目录。"""
    import src.app.services.everos_service as everos_service

    root = tmp_path / "memory"
    root.mkdir()
    monkeypatch.setattr(everos_service, "memory_root", lambda: root)
    return root


@pytest.fixture
def mock_handler():
    async def _handler(request):
        return request
    return AsyncMock(side_effect=_handler)


class TestCatalogFormat:
    def test_subjects_extracted_with_date_label(self, memory_root):
        (memory_root / "smart-test" / "default" / "users" / "platform" / "episodes").mkdir(
            parents=True)
        (memory_root / "smart-test" / "default" / "users" / "platform" / "episodes"
         / "episode-2026-08-31.md").write_text(EPISODE_MD, encoding="utf-8")

        block = build_memory_catalog()

        assert "<agent_memories>" in block
        assert "search_memories" in block
        assert "- [2026-08-31] 第一条记忆主题行" in block
        assert "- [2026-08-31] 第二条记忆主题行" in block

    def test_only_episodes_and_profile_scanned(self, memory_root):
        """原子事实（标题是内部 ID）不进目录。"""
        user_dir = memory_root / "smart-test" / "default" / "users" / "platform"
        (user_dir / ".atomic_facts").mkdir(parents=True)
        (user_dir / ".atomic_facts" / "atomic_fact-2026-08-31.md").write_text(
            "## af_20260831_00000001\n内部原子事实\n", encoding="utf-8")

        block = build_memory_catalog()
        assert block == ""

    def test_empty_root_gives_empty_block(self, memory_root):
        assert build_memory_catalog() == ""

    def test_long_subject_truncated(self, memory_root):
        eps = memory_root / "episodes"
        eps.mkdir(parents=True)
        (eps / "episode-2026-08-30.md").write_text(
            f"### Subject\n{'长' * 200}\n", encoding="utf-8")

        block = build_memory_catalog()

        line = [l for l in block.splitlines() if l.startswith("- [")][0]
        assert "长" * 80 + "…" in line
        assert "长" * 81 not in line

    def test_disabled_feature_gives_empty_block(self, memory_root, monkeypatch):
        from src.app.core.config import settings

        monkeypatch.setattr(settings, "everos_enabled", False)
        assert build_memory_catalog() == ""


class TestInjection:
    @pytest.mark.asyncio
    async def test_appends_to_string_system_message(self, memory_root, mock_handler):
        eps = memory_root / "episodes"
        eps.mkdir(parents=True)
        (eps / "episode-2026-08-31.md").write_text(
            "### Subject\n主题内容\n", encoding="utf-8")
        request = MockModelRequest(
            messages=[],
            system_message=SystemMessage(content="BASE PROMPT"),
        )
        middleware = MemoryInjectionMiddleware()

        await middleware.awrap_model_call(request, mock_handler)

        called_req = mock_handler.call_args[0][0]
        assert called_req.system_message.content.startswith("BASE PROMPT")
        assert "<agent_memories>" in called_req.system_message.content
        assert "主题内容" in called_req.system_message.content

    @pytest.mark.asyncio
    async def test_no_memories_leaves_prompt_untouched(self, memory_root, mock_handler):
        request = MockModelRequest(
            messages=[],
            system_message=SystemMessage(content="BASE PROMPT"),
        )
        middleware = MemoryInjectionMiddleware()

        await middleware.awrap_model_call(request, mock_handler)

        called_req = mock_handler.call_args[0][0]
        assert called_req.system_message.content == "BASE PROMPT"


class TestCache:
    def test_second_call_hits_cache(self, memory_root):
        eps = memory_root / "episodes"
        eps.mkdir(parents=True)
        (eps / "episode-2026-08-31.md").write_text(
            "### Subject\n主题\n", encoding="utf-8")

        first = build_memory_catalog()
        second = build_memory_catalog()

        assert first == second  # byte-stable: prompt prefix caching stays valid

    def test_invalidate_forces_rescan(self, memory_root):
        eps = memory_root / "episodes"
        eps.mkdir(parents=True)
        ep = eps / "episode-2026-08-31.md"
        ep.write_text("### Subject\n主题A\n", encoding="utf-8")

        build_memory_catalog()
        ep.write_text("### Subject\n主题B\n", encoding="utf-8")
        invalidate_memory_cache()

        assert "主题B" in build_memory_catalog()
