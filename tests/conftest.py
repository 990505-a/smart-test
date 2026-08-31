"""Shared pytest fixtures for the smart-test-platform test suite."""
import base64
import io
import sys
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

# Production (LangGraph agent server) imports the app package both as "app"
# and "src.app"; mirror that here so lazy imports inside modules resolve.
_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


@pytest.fixture
def sample_pdf_bytes():
    """Create a minimal valid PDF with real text content that PyMuPDF4LLM can parse."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 750, "Test Document Content")
    c.save()
    return buf.getvalue()


@pytest.fixture
def another_pdf_bytes():
    """Create a second different PDF for cache differentiation tests."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 750, "Different Document Content")
    c.save()
    return buf.getvalue()


@pytest.fixture
def cache_dict():
    """Empty cache dictionary for testing MD5 caching."""
    return {}


class MockModelRequest:
    """Mock ModelRequest for middleware testing."""

    def __init__(self, messages, system_message=None):
        self.messages = messages
        self.system_message = system_message

    def override(self, **kwargs):
        new_req = MockModelRequest(
            messages=kwargs.get("messages", self.messages),
            system_message=kwargs.get("system_message", self.system_message),
        )
        new_req.model = kwargs.get("model", getattr(self, "model", None))
        return new_req


@pytest.fixture
def mock_model_request():
    """Factory fixture for creating MockModelRequest instances."""
    return MockModelRequest


def create_pdf_attachment(filename="doc.pdf", content=b"fake_pdf_content"):
    """Helper to create a PDF attachment dict for middleware tests."""
    return {
        "type": "file",
        "mimeType": "application/pdf",
        "data": base64.b64encode(content).decode(),
        "metadata": {"filename": filename},
    }


@pytest.fixture
def sample_excel_bytes():
    """Create a minimal valid Excel file with test content."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "TestSheet"
    ws.append(["Name", "Value", "Status"])
    ws.append(["item1", 100, "active"])
    ws.append(["item2", 200, "inactive"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def create_image_attachment(filename="test.png", content=b"fake_image_content"):
    """Helper to create an image attachment dict for middleware tests."""
    return {
        "type": "file",
        "mimeType": "image/png",
        "data": base64.b64encode(content).decode(),
        "metadata": {"filename": filename},
    }


def create_excel_attachment(filename="data.xlsx", content=b"fake_excel_content"):
    """Helper to create an Excel attachment dict for middleware tests."""
    return {
        "type": "file",
        "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "data": base64.b64encode(content).decode(),
        "metadata": {"filename": filename},
    }
