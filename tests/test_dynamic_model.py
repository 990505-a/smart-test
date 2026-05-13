"""Unit tests for DynamicModelSelection middleware (MIDW-04, PARS-06)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from tests.conftest import MockModelRequest


@pytest.fixture
def mock_vision_model():
    model = MagicMock()
    model.name = "gpt-4o"
    return model


@pytest.fixture
def dynamic_middleware(mock_vision_model):
    with patch("src.app.middleware.dynamic_model.init_chat_model", return_value=mock_vision_model):
        from src.app.middleware.dynamic_model import DynamicModelSelection
        return DynamicModelSelection(api_key="test-key")


@pytest.fixture
def mock_handler():
    """Create an async mock handler that returns the request."""
    async def _handler(request):
        return request
    return AsyncMock(side_effect=_handler)


class TestNoImagePassesThrough:
    """Text-only messages should NOT trigger model override."""

    @pytest.mark.asyncio
    async def test_no_image_passes_through(self, dynamic_middleware, mock_handler):
        """Messages with only text -> model NOT overridden."""
        msg = HumanMessage(content="Just a text message")
        request = MockModelRequest(
            messages=[msg],
            system_message=SystemMessage(content="System prompt"),
        )

        result = await dynamic_middleware.awrap_model_call(request, mock_handler)

        called_req = mock_handler.call_args[0][0]
        assert getattr(called_req, "model", None) is None


class TestImageUrlTriggersSwitch:
    """image_url content blocks in HumanMessage should trigger model override."""

    @pytest.mark.asyncio
    async def test_image_url_in_content_triggers_switch(self, dynamic_middleware, mock_handler):
        """HumanMessage with image_url content block -> model overridden."""
        msg = HumanMessage(
            content=[
                {"type": "text", "text": "Describe this image"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc123"}},
            ]
        )
        request = MockModelRequest(
            messages=[msg],
            system_message=SystemMessage(content="System prompt"),
        )

        result = await dynamic_middleware.awrap_model_call(request, mock_handler)

        called_req = mock_handler.call_args[0][0]
        assert called_req.model is not None


class TestImageAttachmentTriggersSwitch:
    """image/* MIME attachments should trigger model override."""

    @pytest.mark.asyncio
    async def test_image_attachment_triggers_switch(self, dynamic_middleware, mock_handler):
        """HumanMessage with image/png attachment -> model overridden."""
        import base64
        msg = HumanMessage(
            content="Check this image",
            additional_kwargs={
                "attachments": [{
                    "type": "file",
                    "mimeType": "image/png",
                    "data": base64.b64encode(b"fake_image").decode(),
                    "metadata": {"filename": "screenshot.png"},
                }]
            },
        )
        request = MockModelRequest(
            messages=[msg],
            system_message=SystemMessage(content="System prompt"),
        )

        result = await dynamic_middleware.awrap_model_call(request, mock_handler)

        called_req = mock_handler.call_args[0][0]
        assert called_req.model is not None


class TestPdfAttachmentNoTrigger:
    """PDF attachments should NOT trigger model override."""

    @pytest.mark.asyncio
    async def test_pdf_attachment_does_not_trigger(self, dynamic_middleware, mock_handler):
        """HumanMessage with PDF attachment -> model NOT overridden."""
        import base64
        msg = HumanMessage(
            content="Analyze this PDF",
            additional_kwargs={
                "attachments": [{
                    "type": "file",
                    "mimeType": "application/pdf",
                    "data": base64.b64encode(b"fake_pdf").decode(),
                    "metadata": {"filename": "doc.pdf"},
                }]
            },
        )
        request = MockModelRequest(
            messages=[msg],
            system_message=SystemMessage(content="System prompt"),
        )

        result = await dynamic_middleware.awrap_model_call(request, mock_handler)

        called_req = mock_handler.call_args[0][0]
        assert getattr(called_req, "model", None) is None


class TestImageInNonLastMessage:
    """Image in any message (not just last) should be detected."""

    @pytest.mark.asyncio
    async def test_multiple_messages_with_image(self, dynamic_middleware, mock_handler):
        """Image in non-last message -> still detected (scan ALL messages)."""
        msg_with_image = HumanMessage(
            content=[
                {"type": "text", "text": "Here's an image"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
            ]
        )
        msg_text_only = HumanMessage(content="Follow-up text")

        request = MockModelRequest(
            messages=[msg_with_image, msg_text_only],
            system_message=SystemMessage(content="System prompt"),
        )

        result = await dynamic_middleware.awrap_model_call(request, mock_handler)

        called_req = mock_handler.call_args[0][0]
        assert called_req.model is not None
