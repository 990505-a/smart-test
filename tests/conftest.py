"""Shared pytest fixtures for the smart-test-platform test suite."""
import base64
import io

import pytest
from reportlab.pdfgen import canvas


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
