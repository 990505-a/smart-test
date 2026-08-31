"""Dynamic model selection middleware (DynamicModelSelection).

Per D-01, D-02, D-04: Detects image content in messages and overrides the
LLM model to a vision-capable model.

Detection logic (D-02):
1. Scan all HumanMessages in request.messages.
2. Check msg.content for list-typed content blocks with "type": "image_url".
3. Check msg.additional_kwargs["attachments"] for MIME types starting with "image/".

Model override (D-01):
- When image content is detected, call request.override(model=self._vision_model)
  to switch the LLM from the default text model to the vision model.
- The vision model normally comes prebuilt from model_factory.build_vision_model()
  (explicit vision settings, falling back to the text model). The legacy
  api_key/vision_model kwargs kept for tests and standalone use.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.middleware.types import ResponseT
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langgraph.typing import ContextT


class DynamicModelSelection(AgentMiddleware):
    """Middleware that detects image content and switches to a vision model.

    When image_url content blocks or image/* MIME attachments are found in
    any HumanMessage, this middleware overrides request.model to a
    vision-capable model.
    """

    def __init__(
        self,
        model: BaseChatModel | Callable[[], BaseChatModel] | None = None,
        api_key: str = "",
        vision_model: str = "openai:gpt-4o",
    ):
        """Initialize with a vision model for image content.

        Args:
            model: Prebuilt vision model or a zero-arg factory (preferred —
                pass model_factory.build_vision_model so it rebuilds from the
                latest settings on each image turn, without an agent restart).
            api_key: OpenAI API key for the legacy default vision model.
            vision_model: Model identifier in init_chat_model format.
        """
        if model is not None:
            self._factory: Callable[[], BaseChatModel] = (
                model if callable(model) else (lambda m=model: m)
            )
            return
        kwargs = {"model": vision_model}
        if api_key:
            kwargs["api_key"] = api_key
        built = init_chat_model(**kwargs)
        self._factory = lambda: built

    @property
    def _vision_model(self) -> BaseChatModel:
        """Resolve the vision model per image turn (factory may read fresh settings)."""
        return self._factory()

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
