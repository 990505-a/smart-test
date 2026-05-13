"""Unit tests for FileContextMiddleware (formerly PDFContextMiddleware) with session isolation."""
import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from src.app.middleware.pdf_context import FileContextMiddleware, PDFContextMiddleware
from tests.conftest import MockModelRequest, create_pdf_attachment


@pytest.fixture
def middleware():
    """Create a FileContextMiddleware with a test system prompt."""
    return FileContextMiddleware(
        original_system_prompt="You are a test assistant.",
        enable_cache=True,
    )


@pytest.fixture
def mock_handler():
    """Create an async mock handler that returns the request."""
    async def _handler(request):
        return request
    return AsyncMock(side_effect=_handler)


class TestPDFExtraction:
    """Tests for PDF extraction from HumanMessage attachments."""

    @pytest.mark.asyncio
    async def test_extract_pdf_from_attachments(self, middleware, mock_handler):
        """PDFContextMiddleware extracts PDF and adds document block to system_message."""
        attachment = create_pdf_attachment(filename="doc.pdf", content=b"fake_pdf_data")
        msg = HumanMessage(
            content="Please analyze this document",
            additional_kwargs={"attachments": [attachment]},
        )
        request = MockModelRequest(
            messages=[msg],
            system_message=SystemMessage(content="You are a test assistant."),
        )

        with patch.object(middleware, "_get_thread_id", return_value="thread-1"):
            with patch.object(
                middleware._pdf_processor, "extract_text", return_value="Extracted PDF content here"
            ):
                result = await middleware.awrap_model_call(request, mock_handler)

        # The handler should have been called with an overridden system_message
        called_req = mock_handler.call_args[0][0]
        assert "<document>" in called_req.system_message.content
        assert "Extracted PDF content here" in called_req.system_message.content

    @pytest.mark.asyncio
    async def test_image_attachment_processed(self, middleware, mock_handler):
        """Image attachments (e.g., image/png) are now processed by ImageProcessor."""
        image_attachment = {
            "type": "file",
            "mimeType": "image/png",
            "data": base64.b64encode(b"fake_image").decode(),
            "metadata": {"filename": "screenshot.png"},
        }
        msg = HumanMessage(
            content="Look at this image",
            additional_kwargs={"attachments": [image_attachment]},
        )
        request = MockModelRequest(
            messages=[msg],
            system_message=SystemMessage(content="You are a test assistant."),
        )

        with patch.object(middleware, "_get_thread_id", return_value="thread-1"):
            with patch.object(
                middleware._image_processor, "extract_text", return_value="Image description text"
            ):
                result = await middleware.awrap_model_call(request, mock_handler)

        # system_message should contain the image description as a document block
        called_req = mock_handler.call_args[0][0]
        assert "<document>" in called_req.system_message.content
        assert "Image description text" in called_req.system_message.content


class TestSessionIsolation:
    """Tests for thread_id level session isolation."""

    @pytest.mark.asyncio
    async def test_session_isolation(self, middleware, mock_handler):
        """Different thread_ids maintain separate document state."""
        attachment = create_pdf_attachment(filename="doc.pdf", content=b"pdf_data_A")
        msg_a = HumanMessage(
            content="Analyze this",
            additional_kwargs={"attachments": [attachment]},
        )
        msg_b = HumanMessage(content="Hello, no PDF here")

        with patch.object(
            middleware._pdf_processor, "extract_text", return_value="Content for A"
        ):
            # Thread A: Upload PDF
            req_a = MockModelRequest(
                messages=[msg_a],
                system_message=SystemMessage(content="System prompt"),
            )
            with patch.object(middleware, "_get_thread_id", return_value="thread-A"):
                await middleware.awrap_model_call(req_a, mock_handler)

            # Thread B: No PDF
            req_b = MockModelRequest(
                messages=[msg_b],
                system_message=SystemMessage(content="System prompt"),
            )
            with patch.object(middleware, "_get_thread_id", return_value="thread-B"):
                result = await middleware.awrap_model_call(req_b, mock_handler)

        # Thread B should NOT have the document
        called_req = mock_handler.call_args[0][0]
        assert "<document>" not in called_req.system_message.content


class TestImmutableSystemPrompt:
    """Tests for immutable system prompt pattern."""

    @pytest.mark.asyncio
    async def test_immutable_system_prompt_preserves_content(self, middleware, mock_handler):
        """PDF injection preserves existing system_message content."""
        attachment = create_pdf_attachment(filename="doc.pdf", content=b"pdf_data")
        msg = HumanMessage(
            content="Analyze",
            additional_kwargs={"attachments": [attachment]},
        )
        original_content = "Original skills content here"
        request = MockModelRequest(
            messages=[msg],
            system_message=SystemMessage(content=original_content),
        )

        with patch.object(middleware, "_get_thread_id", return_value="thread-1"):
            with patch.object(
                middleware._pdf_processor, "extract_text", return_value="PDF text"
            ):
                result = await middleware.awrap_model_call(request, mock_handler)

        called_req = mock_handler.call_args[0][0]
        content = called_req.system_message.content
        # Must preserve original content
        assert "Original skills content here" in content
        # Must also contain the document block
        assert "<document>" in content


class TestMD5Dedup:
    """Tests for MD5-based deduplication of same PDF in same thread."""

    @pytest.mark.asyncio
    async def test_md5_dedup_same_pdf(self, middleware, mock_handler):
        """Same PDF bytes in same thread do not trigger re-parsing."""
        attachment = create_pdf_attachment(filename="doc.pdf", content=b"same_pdf_bytes")
        msg = HumanMessage(
            content="Analyze",
            additional_kwargs={"attachments": [attachment]},
        )

        extract_mock = MagicMock(return_value="PDF text")

        with patch.object(middleware, "_get_thread_id", return_value="thread-1"):
            with patch.object(middleware._pdf_processor, "extract_text", extract_mock):
                # First call
                req1 = MockModelRequest(
                    messages=[msg],
                    system_message=SystemMessage(content="System"),
                )
                await middleware.awrap_model_call(req1, mock_handler)

                # Second call with same PDF
                req2 = MockModelRequest(
                    messages=[msg],
                    system_message=SystemMessage(content="System"),
                )
                await middleware.awrap_model_call(req2, mock_handler)

        # extract_text should be called only once (dedup on second call)
        assert extract_mock.call_count == 1


class TestOnlyLastMessageScanned:
    """Tests for only scanning the last user message for PDFs."""

    @pytest.mark.asyncio
    async def test_only_last_message_scanned(self, middleware, mock_handler):
        """Only the last user message is scanned for PDF attachments."""
        pdf_attachment = create_pdf_attachment(filename="old.pdf", content=b"old_pdf")
        msg_with_pdf = HumanMessage(
            content="Old message with PDF",
            additional_kwargs={"attachments": [pdf_attachment]},
        )
        msg_no_pdf = HumanMessage(content="Latest message without PDF")

        request = MockModelRequest(
            messages=[msg_with_pdf, msg_no_pdf],
            system_message=SystemMessage(content="System prompt"),
        )

        with patch.object(middleware, "_get_thread_id", return_value="thread-1"):
            result = await middleware.awrap_model_call(request, mock_handler)

        # No document should be injected (last message has no PDF)
        called_req = mock_handler.call_args[0][0]
        assert "<document>" not in called_req.system_message.content


class TestFallbackThreadId:
    """Tests for fallback thread_id behavior."""

    @pytest.mark.asyncio
    async def test_fallback_thread_id(self, middleware, mock_handler):
        """When get_config() fails, middleware uses __default__ and still works."""
        attachment = create_pdf_attachment(filename="doc.pdf", content=b"fallback_pdf")
        msg = HumanMessage(
            content="Analyze",
            additional_kwargs={"attachments": [attachment]},
        )
        request = MockModelRequest(
            messages=[msg],
            system_message=SystemMessage(content="System"),
        )

        # The real _get_thread_id should work even without LangGraph context
        # It falls back to "__default__"
        with patch.object(
            middleware._pdf_processor, "extract_text", return_value="Fallback content"
        ):
            result = await middleware.awrap_model_call(request, mock_handler)

        called_req = mock_handler.call_args[0][0]
        # Should still work with __default__ thread
        assert "<document>" in called_req.system_message.content


class TestClearSession:
    """Tests for session management methods."""

    @pytest.mark.asyncio
    async def test_clear_session(self, middleware, mock_handler):
        """clear_session removes document state for specified thread."""
        attachment = create_pdf_attachment(filename="doc.pdf", content=b"test_pdf")
        msg = HumanMessage(
            content="Analyze",
            additional_kwargs={"attachments": [attachment]},
        )

        with patch.object(middleware, "_get_thread_id", return_value="thread-X"):
            with patch.object(
                middleware._pdf_processor, "extract_text", return_value="Content"
            ):
                req = MockModelRequest(
                    messages=[msg],
                    system_message=SystemMessage(content="System"),
                )
                await middleware.awrap_model_call(req, mock_handler)

        # Verify document exists
        assert "thread-X" in middleware._session_docs

        # Clear session
        middleware.clear_session("thread-X")
        assert "thread-X" not in middleware._session_docs
        assert "thread-X" not in middleware._session_file_hash

    def test_get_session_stats(self, middleware):
        """get_session_stats returns expected structure."""
        stats = middleware.get_session_stats()
        assert "active_sessions" in stats
        assert "session_ids" in stats
        assert "doc_lengths" in stats
