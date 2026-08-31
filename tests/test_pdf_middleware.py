"""Unit tests for PDFContextMiddleware (current content-array implementation).

The middleware scans HumanMessage content arrays for `type: "file"` blocks
(PDF / Markdown), saves the payloads to the upload dir, extracts text, and
rewrites the message with the extracted text appended. Unsupported MIME types
and plain messages pass through untouched.
"""
import base64
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from src.app.middleware.pdf_context import FileContextMiddleware, PDFContextMiddleware
from tests.conftest import MockModelRequest, create_pdf_attachment


@pytest.fixture
def middleware(tmp_path, monkeypatch):
    """Middleware with uploads redirected into the test's tmp dir."""
    import src.app.middleware.pdf_context as pdf_context_mod

    monkeypatch.setattr(pdf_context_mod, "_UPLOAD_DIR", tmp_path)
    return PDFContextMiddleware()


@pytest.fixture
def mock_handler():
    """Async handler mock that returns the request it was called with."""
    async def _handler(request):
        return request
    return AsyncMock(side_effect=_handler)


def _file_message(text: str, attachments: list[dict]) -> HumanMessage:
    return HumanMessage(
        content=[{"type": "text", "text": text}, *attachments],
    )


class TestPassthrough:
    @pytest.mark.asyncio
    async def test_plain_message_untouched(self, middleware, mock_handler):
        """No file blocks -> handler receives the original request object."""
        msg = HumanMessage(content="Just text, no files")
        request = MockModelRequest(
            messages=[msg],
            system_message=SystemMessage(content="System"),
        )

        await middleware.awrap_model_call(request, mock_handler)

        assert mock_handler.call_args[0][0] is request

    @pytest.mark.asyncio
    async def test_unsupported_mime_ignored(self, middleware, mock_handler):
        """image/png file blocks are not extracted by this middleware."""
        image_block = {
            "type": "file",
            "mimeType": "image/png",
            "data": base64.b64encode(b"fake_image").decode(),
            "metadata": {"filename": "screenshot.png"},
        }
        msg = _file_message("Look at this", [image_block])
        request = MockModelRequest(
            messages=[msg],
            system_message=SystemMessage(content="System"),
        )

        await middleware.awrap_model_call(request, mock_handler)

        assert mock_handler.call_args[0][0] is request


class TestExtraction:
    @pytest.mark.asyncio
    async def test_markdown_file_extracted_and_stripped(self, middleware, mock_handler, tmp_path):
        """Markdown file block -> text injected into the message, file block removed."""
        md_bytes = "# Title\n\nhello markdown".encode("utf-8")
        block = {
            "type": "file",
            "mimeType": "text/markdown",
            "data": base64.b64encode(md_bytes).decode(),
            "metadata": {"filename": "notes.md"},
        }
        msg = _file_message("Please analyze", [block])
        request = MockModelRequest(
            messages=[msg],
            system_message=SystemMessage(content="System"),
        )

        await middleware.awrap_model_call(request, mock_handler)

        called_req = mock_handler.call_args[0][0]
        assert called_req is not request
        new_msg = called_req.messages[0]
        texts = [b for b in new_msg.content if isinstance(b, dict) and b.get("type") == "text"]
        joined = "".join(t.get("text", "") for t in texts)
        assert "### 文件: notes.md (Markdown)" in joined
        assert "hello markdown" in joined
        assert "[系统提示] 用户上传了 1 个文件" in joined
        # File payload is stripped from the model-visible content
        assert not [b for b in new_msg.content if isinstance(b, dict) and b.get("type") == "file"]
        # Original file was persisted to the (patched) upload dir
        assert len(list(Path(tmp_path).iterdir())) == 1

    @pytest.mark.asyncio
    async def test_pdf_file_extracted_via_processor(self, middleware, mock_handler):
        """PDF file block -> text extracted through app.processors.pdf."""
        block = create_pdf_attachment(filename="doc.pdf", content=b"fake_pdf_data")
        msg = _file_message("Analyze this PDF", [block])
        request = MockModelRequest(
            messages=[msg],
            system_message=SystemMessage(content="System"),
        )

        import app.processors.pdf as pdf_processor_module
        with patch.object(
            pdf_processor_module, "extract_pdf_text", return_value="PDF TEXT CONTENT"
        ):
            await middleware.awrap_model_call(request, mock_handler)

        called_req = mock_handler.call_args[0][0]
        new_msg = called_req.messages[0]
        texts = [b for b in new_msg.content if isinstance(b, dict) and b.get("type") == "text"]
        joined = "".join(t.get("text", "") for t in texts)
        assert "### 文件: doc.pdf (PDF)" in joined
        assert "PDF TEXT CONTENT" in joined

    @pytest.mark.asyncio
    async def test_long_content_truncated(self, middleware, mock_handler):
        """Extracted text beyond the 50k cap is truncated with a marker."""
        md_bytes = ("x" * 60_000).encode("utf-8")
        block = {
            "type": "file",
            "mimeType": "text/markdown",
            "data": base64.b64encode(md_bytes).decode(),
            "metadata": {"filename": "big.md"},
        }
        msg = _file_message("Analyze", [block])
        request = MockModelRequest(
            messages=[msg],
            system_message=SystemMessage(content="System"),
        )

        await middleware.awrap_model_call(request, mock_handler)

        called_req = mock_handler.call_args[0][0]
        new_msg = called_req.messages[0]
        texts = [b for b in new_msg.content if isinstance(b, dict) and b.get("type") == "text"]
        joined = "".join(t.get("text", "") for t in texts)
        assert "文件内容已截断" in joined

    @pytest.mark.asyncio
    async def test_multiple_messages_only_files_rewritten(self, middleware, mock_handler):
        """Messages without file blocks keep their identity; only file messages are replaced."""
        md_block = {
            "type": "file",
            "mimeType": "text/markdown",
            "data": base64.b64encode(b"content").decode(),
            "metadata": {"filename": "a.md"},
        }
        msg_with_file = _file_message("With file", [md_block])
        plain_msg = HumanMessage(content="No file here")
        request = MockModelRequest(
            messages=[msg_with_file, plain_msg],
            system_message=SystemMessage(content="System"),
        )

        await middleware.awrap_model_call(request, mock_handler)

        called_req = mock_handler.call_args[0][0]
        assert called_req.messages[1] is plain_msg
        assert called_req.messages[0] is not msg_with_file
