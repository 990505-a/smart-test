"""Dynamic model selection middleware (DynamicModelSelection).

Per D-01, D-02, D-04: Detects image content in messages and overrides the
LLM model to GPT-4o for vision-capable inference.

Detection logic (D-02):
1. Scan all HumanMessages in request.messages.
2. Check msg.content for list-typed content blocks with "type": "image_url".
3. Check msg.additional_kwargs["attachments"] for MIME types starting with "image/".

Model override (D-01):
- When image content is detected, call request.override(model=self._vision_model)
  to switch the LLM from the default text model to GPT-4o.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.middleware.types import ResponseT
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage
from langgraph.typing import ContextT


class DynamicModelSelection(AgentMiddleware):
    """Middleware that detects image content and switches to a vision model.

    When image_url content blocks or image/* MIME attachments are found in
    any HumanMessage, this middleware overrides request.model to a vision-capable
    model (default: GPT-4o).
    """

    def __init__(
        self,
        api_key: str = "",
        vision_model: str = "openai:gpt-4o",
    ):
        """Initialize with a vision model for image content.

        Args:
            api_key: OpenAI API key for the vision model.
            vision_model: Model identifier in init_chat_model format.
        """
        kwargs = {"model": vision_model}
        if api_key:
            kwargs["api_key"] = api_key
        self._vision_model = init_chat_model(**kwargs)

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> Any:
        """Intercept LLM call, switch model if image content detected."""
        if self._has_image_content(request):
            request = request.override(model=self._vision_model)
        return await handler(request)

    def _has_image_content(self, request: ModelRequest) -> bool:
        """Check if any HumanMessage contains image content.

        Per D-02, checks two sources:
        1. msg.content list blocks with "type": "image_url"
        2. msg.additional_kwargs["attachments"] with mimeType starting with "image/"

        Args:
            request: The model request to inspect.

        Returns:
            True if image content is found, False otherwise.
        """
        for msg in request.messages:
            if not isinstance(msg, HumanMessage):
                continue

            # Check content blocks for image_url type
            content = msg.content
            if isinstance(content, list):
                for block in content:
                    if (
                        isinstance(block, dict)
                        and block.get("type") == "image_url"
                    ):
                        return True

            # Check attachments for image MIME types
            attachments = msg.additional_kwargs.get("attachments", [])
            if isinstance(attachments, list):
                for att in attachments:
                    if isinstance(att, dict):
                        mime_type = att.get("mimeType", "")
                        if mime_type.startswith("image/"):
                            return True

        return False
