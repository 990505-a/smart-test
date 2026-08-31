"""Unit tests for MemoryInjectionMiddleware (catalog-style injection + cache)."""
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import SystemMessage

import src.app.middleware.memory_injection as memory_injection
from src.app.middleware.memory_injection import (
    MemoryInjectionMiddleware,
    invalidate_memory_cache,
)
from tests.conftest import MockModelRequest


def _make_memory(key: str, content: str, category: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(key=key, content=content, category=category)


class _FakeSessionFactory:
    """Stand-in for async_session_factory returning canned memory rows."""

    def __init__(self, rows: list):
        self.rows = rows
        self.calls = 0
        self.statements = []

    def __call__(self):
        self.calls += 1
        rows = self.rows
        statements = self.statements

        @asynccontextmanager
        async def _ctx():
            async def _execute(stmt):
                statements.append(stmt)
                return SimpleNamespace(
                    scalars=lambda: SimpleNamespace(all=lambda: rows)
                )

            yield SimpleNamespace(execute=_execute)

        return _ctx()


@pytest.fixture(autouse=True)
def _reset_cache():
    invalidate_memory_cache()
    yield
    invalidate_memory_cache()


@pytest.fixture
def mock_handler():
    async def _handler(request):
        return request
    return AsyncMock(side_effect=_handler)


@pytest.fixture
def patch_db(monkeypatch):
    """Patch the DB session factory; returns the factory for row setup."""
    import src.app.db.database as db_module

    factory = _FakeSessionFactory(rows=[])
    monkeypatch.setattr(db_module, "async_session_factory", factory)
    return factory


class TestCatalogFormat:
    @pytest.mark.asyncio
    async def test_catalog_line_format_and_preview_truncation(self, patch_db):
        patch_db.rows = [
            _make_memory("pref_lang", "v" * 200, category="preference"),
        ]

        block = await MemoryInjectionMiddleware._load_memory_catalog()

        assert "<agent_memories>" in block
        assert "search_memories" in block
        assert "- [preference] pref_lang: " in block
        # Preview capped at 80 chars + ellipsis
        line = [l for l in block.splitlines() if l.startswith("- [preference]")][0]
        assert "v" * 80 + "…" in line
        assert "v" * 81 not in line

    @pytest.mark.asyncio
    async def test_uncategorized_label(self, patch_db):
        patch_db.rows = [_make_memory("k1", "short content", category=None)]

        block = await MemoryInjectionMiddleware._load_memory_catalog()

        assert "- [未分类] k1: short content" in block

    @pytest.mark.asyncio
    async def test_entry_limit_enforced_in_query(self, patch_db):
        """The catalog query itself is LIMIT-bounded (the DB does the capping)."""
        patch_db.rows = [
            _make_memory(f"key_{i}", f"content {i}") for i in range(20)
        ]

        block = await MemoryInjectionMiddleware._load_memory_catalog()

        assert "<agent_memories>" in block
        assert patch_db.statements[0]._limit == memory_injection.MAX_ENTRIES

    @pytest.mark.asyncio
    async def test_block_size_bounded(self, patch_db):
        """Oversized catalogs are truncated with a marker instead of growing the prompt."""
        patch_db.rows = [
            _make_memory("k" * 300, "content") for _ in range(15)
        ]

        block = await MemoryInjectionMiddleware._load_memory_catalog()

        assert "已截断" in block
        assert len(block) <= memory_injection.MAX_BLOCK_CHARS + 300  # block + wrapper text

    @pytest.mark.asyncio
    async def test_multiline_content_flattened_in_preview(self, patch_db):
        patch_db.rows = [_make_memory("k", "line1\nline2", category="c")]

        block = await MemoryInjectionMiddleware._load_memory_catalog()

        assert "line1 line2" in block


class TestInjection:
    @pytest.mark.asyncio
    async def test_appends_to_string_system_message(self, patch_db, mock_handler):
        patch_db.rows = [_make_memory("k", "content", category="c")]
        request = MockModelRequest(
            messages=[],
            system_message=SystemMessage(content="BASE PROMPT"),
        )
        middleware = MemoryInjectionMiddleware()

        await middleware.awrap_model_call(request, mock_handler)

        called_req = mock_handler.call_args[0][0]
        assert called_req.system_message.content.startswith("BASE PROMPT")
        assert "<agent_memories>" in called_req.system_message.content

    @pytest.mark.asyncio
    async def test_no_memories_leaves_prompt_untouched(self, patch_db, mock_handler):
        patch_db.rows = []
        request = MockModelRequest(
            messages=[],
            system_message=SystemMessage(content="BASE PROMPT"),
        )
        middleware = MemoryInjectionMiddleware()

        await middleware.awrap_model_call(request, mock_handler)

        called_req = mock_handler.call_args[0][0]
        assert called_req.system_message.content == "BASE PROMPT"

    @pytest.mark.asyncio
    async def test_db_failure_passes_through(self, patch_db, mock_handler):
        def _boom():
            raise RuntimeError("db down")

        patch_db.__call__ = _boom
        request = MockModelRequest(
            messages=[],
            system_message=SystemMessage(content="BASE PROMPT"),
        )
        middleware = MemoryInjectionMiddleware()

        await middleware.awrap_model_call(request, mock_handler)

        called_req = mock_handler.call_args[0][0]
        assert called_req.system_message.content == "BASE PROMPT"


class TestCache:
    @pytest.mark.asyncio
    async def test_second_call_hits_cache(self, patch_db):
        patch_db.rows = [_make_memory("k", "content")]

        await MemoryInjectionMiddleware._load_memory_catalog()
        await MemoryInjectionMiddleware._load_memory_catalog()

        assert patch_db.calls == 1

    @pytest.mark.asyncio
    async def test_invalidate_forces_reload(self, patch_db):
        patch_db.rows = [_make_memory("k", "content")]

        await MemoryInjectionMiddleware._load_memory_catalog()
        invalidate_memory_cache()
        await MemoryInjectionMiddleware._load_memory_catalog()

        assert patch_db.calls == 2

    def test_invalidate_clears_under_every_module_alias(self):
        """Aliases ("app." / "src.app.") must not diverge — invalidate clears both."""
        import sys

        memory_injection._cached_block = "stale"
        memory_injection._cached_at = 0.0

        invalidate_memory_cache()

        for name in memory_injection._MODULE_ALIASES:
            mod = sys.modules.get(name)
            if mod is not None:
                assert mod._cached_block is None
