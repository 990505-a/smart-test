"""Image processor using GPT-4o vision model (ImageProcessor).

Per D-06: Extracts text from images via ChatOpenAI(model=gpt-4o).
Sends base64-encoded image data to GPT-4o with a Chinese language prompt
that instructs the model to describe text, UI elements, layout, and
functional points in detail.
"""

from __future__ import annotations

import base64
import logging
from pathlib import PurePosixPath

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

_VISION_PROMPT = (
    "请详细描述这张图片中的所有文字、UI元素、布局结构和功能点。"
    "如果图片包含测试相关的需求文档、流程图或界面设计，请完整提取其中的信息。"
)

# Extension to MIME type mapping
_MIME_MAP: dict[str, str] = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
}


def _infer_mime(filename: str) -> str:
    """Infer MIME type from filename extension."""
    ext = PurePosixPath(filename).suffix.lower().lstrip(".")
    return _MIME_MAP.get(ext, "image/png")


class ImageProcessor:
    """Image processor that uses GPT-4o vision to extract text from images.

    Sends a base64-encoded image to OpenAI's GPT-4o model with a structured
    prompt requesting detailed description of all text, UI elements, layouts,
    and functional points.
    """

    def __init__(self, api_key: str = ""):
        """Initialize the image processor.

        Args:
            api_key: OpenAI API key. If empty, relies on environment variable.
        """
        self._api_key = api_key
        self._model = None  # Lazy initialization to avoid API key errors at import time

    def _get_model(self):
        """Lazy-initialize the vision model on first use."""
        if self._model is None:
            kwargs = {"model": "openai:gpt-4o"}
            if self._api_key:
                kwargs["api_key"] = self._api_key
            self._model = init_chat_model(**kwargs)
        return self._model

    def extract_text(self, image_data: bytes, filename: str = "image.png") -> str:
        """Extract text description from image bytes using GPT-4o vision.

        Args:
            image_data: Raw image file bytes.
            filename: Original filename for MIME type inference.

        Returns:
            Text description of the image content.
        """
        if not image_data:
            return ""

        try:
            mime = _infer_mime(filename)
            b64 = base64.b64encode(image_data).decode("utf-8")

            message = HumanMessage(
                content=[
                    {"type": "text", "text": _VISION_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    },
                ]
            )

            response = self._get_model().invoke([message])
            return response.content
        except Exception as e:
            logger.error("ImageProcessor: failed to extract text from %s: %s", filename, e)
            return f"Image processing error: {e}"
