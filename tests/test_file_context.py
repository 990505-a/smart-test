"""Unit tests for FileContextMiddleware (PARS-02, PARS-03, PARS-06)."""
import base64
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import HumanMessage, SystemMessage

from src.app.middleware.pdf_context import FileContextMiddleware
from tests.conftest import (
    MockModelRequest,
    create_pdf_attachment,
    create_image_attachment,
    create_excel_attachment,
)


@pytest.fixture
def middleware():
    """Create a FileContextMiddleware with mocked processors."""
    with patch("src.app.middleware.pdf_context.ImageProcessor") as MockImgProc, \
         patch("src.app.middleware.pdf_context.PDFProcessor") as MockPdfProc, \
         patch("src.app.middleware.pdf_context.ExcelProcessor") as MockExcelProc:
        mw = FileContextMiddleware(
            original_system_prompt="You are a test assistant.",
            enable_cache=True,
            api_key="test-key",
        )
        yield mw


@pytest.fixture
def mock_handler():
    """Create an async mock handler that returns the request."""
    async def _handler(request):
        return request
    return AsyncMock(side_effect=_handler)


# ---------------------------------------------------------------------------
# ExcelProcessor tests (using real openpyxl data)
# ---------------------------------------------------------------------------


class TestExcelProcessor:
    """Tests for ExcelProcessor with real openpyxl data."""

    def test_excel_processor_extracts_markdown(self, sample_excel_bytes):
        """ExcelProcessor converts sample Excel to Markdown table."""
        from src.app.processors.excel import ExcelProcessor
        processor = ExcelProcessor()
        result = processor.extract_text(sample_excel_bytes, "test.xlsx")

        assert "| Name | Value | Status |" in result
        assert "| item1 | 100 | active |" in result
        assert "| item2 | 200 | inactive |" in result
        assert "### Sheet: TestSheet" in result

    def test_excel_processor_empty_input(self):
        """Empty bytes returns empty string."""
        from src.app.processors.excel import ExcelProcessor
        processor = ExcelProcessor()
        result = processor.extract_text(b"", "empty.xlsx")
        assert result == ""

    def test_excel_processor_multi_sheet(self):
        """Workbook with 2 sheets contains both sheet headings."""
        from openpyxl import Workbook
        import io

        wb = Workbook()
        ws1 = wb.active
        ws1.title = "Sheet1"
        ws1.append(["A", "B"])
        ws1.append(["1", "2"])

        ws2 = wb.create_sheet("Sheet2")
        ws2.append(["X", "Y"])
        ws2.append(["10", "20"])

        buf = io.BytesIO()
        wb.save(buf)

        from src.app.processors.excel import ExcelProcessor
        processor = ExcelProcessor()
        result = processor.extract_text(buf.getvalue(), "multi.xlsx")

        assert "### Sheet: Sheet1" in result
        assert "### Sheet: Sheet2" in result


# ---------------------------------------------------------------------------
# FileContextMiddleware dispatch tests (mocked processors)
# ---------------------------------------------------------------------------


class TestPDFDispatch:
    """PDF files are dispatched to PDFProcessor."""

    @pytest.mark.asyncio
    async def test_pdf_dispatch(self, middleware, mock_handler):
        """PDF attachment -> calls pdf_processor.extract_text."""
        attachment = create_pdf_attachment(filename="doc.pdf", content=b"pdf_data")
        msg = HumanMessage(
            content="Analyze this PDF",
            additional_kwargs={"attachments": [attachment]},
        )
        request = MockModelRequest(
            messages=[msg],
            system_message=SystemMessage(content="System"),
        )

        with patch.object(middleware, "_get_thread_id", return_value="thread-1"):
            with patch.object(
                middleware._pdf_processor, "extract_text", return_value="PDF content"
            ):
                await middleware.awrap_model_call(request, mock_handler)

        called_req = mock_handler.call_args[0][0]
        assert "<document>" in called_req.system_message.content
        assert "PDF content" in called_req.system_message.content


class TestImageDispatch:
    """Image files are dispatched to ImageProcessor."""

    @pytest.mark.asyncio
    async def test_image_dispatch(self, middleware, mock_handler):
        """Image attachment -> calls image_processor.extract_text."""
        attachment = create_image_attachment(filename="photo.png", content=b"img_data")
        msg = HumanMessage(
            content="Describe this image",
            additional_kwargs={"attachments": [attachment]},
        )
        request = MockModelRequest(
            messages=[msg],
            system_message=SystemMessage(content="System"),
        )

        with patch.object(middleware, "_get_thread_id", return_value="thread-1"):
            with patch.object(
                middleware._image_processor, "extract_text", return_value="Image description"
            ):
                await middleware.awrap_model_call(request, mock_handler)

        called_req = mock_handler.call_args[0][0]
        assert "<document>" in called_req.system_message.content
        assert "Image description" in called_req.system_message.content


class TestExcelDispatch:
    """Excel files are dispatched to ExcelProcessor."""

    @pytest.mark.asyncio
    async def test_excel_dispatch(self, middleware, mock_handler):
        """Excel attachment -> calls excel_processor.extract_text."""
        attachment = create_excel_attachment(filename="data.xlsx", content=b"excel_data")
        msg = HumanMessage(
            content="Read this Excel",
            additional_kwargs={"attachments": [attachment]},
        )
        request = MockModelRequest(
            messages=[msg],
            system_message=SystemMessage(content="System"),
        )

        with patch.object(middleware, "_get_thread_id", return_value="thread-1"):
            with patch.object(
                middleware._excel_processor, "extract_text", return_value="Excel content"
            ):
                await middleware.awrap_model_call(request, mock_handler)

        called_req = mock_handler.call_args[0][0]
        assert "<document>" in called_req.system_message.content
        assert "Excel content" in called_req.system_message.content


class TestMultiFileConcatenation:
    """Multiple files in a single message are all processed and concatenated."""

    @pytest.mark.asyncio
    async def test_multi_file_concatenation(self, middleware, mock_handler):
        """PDF + image in same message -> both processed, concatenated in session."""
        pdf_att = create_pdf_attachment(filename="doc.pdf", content=b"pdf_bytes")
        img_att = create_image_attachment(filename="img.png", content=b"img_bytes")
        msg = HumanMessage(
            content="Analyze these files",
            additional_kwargs={"attachments": [pdf_att, img_att]},
        )
        request = MockModelRequest(
            messages=[msg],
            system_message=SystemMessage(content="System"),
        )

        with patch.object(middleware, "_get_thread_id", return_value="thread-1"):
            with patch.object(
                middleware._pdf_processor, "extract_text", return_value="PDF text here"
            ):
                with patch.object(
                    middleware._image_processor, "extract_text", return_value="Image desc here"
                ):
                    await middleware.awrap_model_call(request, mock_handler)

        called_req = mock_handler.call_args[0][0]
        content = called_req.system_message.content
        assert "PDF text here" in content
        assert "Image desc here" in content


class TestSessionIsolation:
    """Different thread_ids maintain independent document state."""

    @pytest.mark.asyncio
    async def test_session_isolation(self, middleware, mock_handler):
        """Two thread_ids have independent document state."""
        pdf_att = create_pdf_attachment(filename="doc.pdf", content=b"pdf_data_A")
        msg_a = HumanMessage(
            content="Analyze",
            additional_kwargs={"attachments": [pdf_att]},
        )
        msg_b = HumanMessage(content="Hello, no files here")

        with patch.object(
            middleware._pdf_processor, "extract_text", return_value="Content for A"
        ):
            # Thread A: Upload file
            req_a = MockModelRequest(
                messages=[msg_a],
                system_message=SystemMessage(content="System"),
            )
            with patch.object(middleware, "_get_thread_id", return_value="thread-A"):
                await middleware.awrap_model_call(req_a, mock_handler)

            # Thread B: No file
            req_b = MockModelRequest(
                messages=[msg_b],
                system_message=SystemMessage(content="System"),
            )
            with patch.object(middleware, "_get_thread_id", return_value="thread-B"):
                await middleware.awrap_model_call(req_b, mock_handler)

        # Thread B should NOT have the document
        called_req = mock_handler.call_args[0][0]
        assert "<document>" not in called_req.system_message.content


class TestMD5Dedup:
    """MD5-based dedup prevents re-parsing same file in same thread."""

    @pytest.mark.asyncio
    async def test_md5_dedup(self, middleware, mock_handler):
        """Same file uploaded twice -> parsed only once."""
        attachment = create_pdf_attachment(filename="doc.pdf", content=b"same_pdf_bytes")
        msg = HumanMessage(
            content="Analyze",
            additional_kwargs={"attachments": [attachment]},
        )

        extract_mock = MagicMock(return_value="Parsed content")

        with patch.object(middleware, "_get_thread_id", return_value="thread-1"):
            with patch.object(middleware._pdf_processor, "extract_text", extract_mock):
                # First call
                req1 = MockModelRequest(
                    messages=[msg],
                    system_message=SystemMessage(content="System"),
                )
                await middleware.awrap_model_call(req1, mock_handler)

                # Second call with same file
                req2 = MockModelRequest(
                    messages=[msg],
                    system_message=SystemMessage(content="System"),
                )
                await middleware.awrap_model_call(req2, mock_handler)

        # extract_text should be called only once (dedup on second call)
        assert extract_mock.call_count == 1
