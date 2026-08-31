"""文件上下文注入中间件 (PDFContextMiddleware)

从 messages 中最后一个用户消息的 content 数组中提取文件块（PDF/Markdown），
将 base64 数据解码后直接提取文本内容，注入到该 HumanMessage 中。

设计决策：文件内容提取在中间件中确定性完成，不依赖 LLM 的工具调用行为。
这确保多文件上传时所有文件的内容都被完整注入，而不会因为 LLM 只调用一次工具
而导致只分析了一个文件。

注意：LangGraph API 会清空 additional_kwargs，所以文件数据必须放在 content 数组中。
"""

from __future__ import annotations

import base64
import logging
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.middleware.types import ResponseT
from langchain_core.messages import HumanMessage
from langgraph.typing import ContextT

logger = logging.getLogger(__name__)

_UPLOAD_DIR = Path(__file__).resolve().parent.parent / "workspace" / "uploads"
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_SUPPORTED_MIME = {"application/pdf", "text/markdown"}

# Maximum characters per file to inject into the prompt.
# Large PDFs can produce hundreds of thousands of characters, overwhelming the LLM context.
_MAX_CONTENT_CHARS = 50_000


def _decode_base64(data: str) -> bytes:
    if "," in data:
        data = data.split(",", 1)[1]
    return base64.b64decode(data)


def _extract_file_blocks(content: Any) -> list[tuple[bytes, str, str]]:
    """Extract file data from content array. Returns [(bytes, filename, mime_type)]."""
    if not isinstance(content, list):
        return []

    results: list[tuple[bytes, str, str]] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "file":
            continue

        mime = block.get("mimeType", "").lower()
        if mime not in _SUPPORTED_MIME:
            continue

        data = block.get("data")
        if not data or not isinstance(data, str):
            continue

        try:
            file_bytes = _decode_base64(data)
            filename = block.get("metadata", {}).get("filename", "document.pdf")
            results.append((file_bytes, filename, mime))
        except Exception as e:
            logger.warning("[PDFContextMiddleware] 文件解码失败: %s", e)

    return results


def _extract_text_from_bytes(file_bytes: bytes, filename: str, mime_type: str) -> str:
    """Extract text content from file bytes based on MIME type.

    For Markdown files, decodes as UTF-8 text.
    For PDF files, uses the extract_pdf_text function from app.processors.pdf.
    """
    if mime_type == "text/markdown":
        try:
            return file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return file_bytes.decode("gbk")
            except UnicodeDecodeError:
                return file_bytes.decode("utf-8", errors="replace")

    # PDF extraction
    try:
        from app.processors.pdf import extract_pdf_text

        return extract_pdf_text(file_bytes, filename)
    except ImportError:
        logger.warning("[PDFContextMiddleware] PDF processor not available, falling back to save-only mode")
        return ""
    except Exception as e:
        logger.error("[PDFContextMiddleware] PDF text extraction failed for %s: %s", filename, e)
        return f"[PDF extraction error: {e}]"


class PDFContextMiddleware(AgentMiddleware):
    """文件上下文注入中间件。

    NOTE: This middleware only works with direct agent.ainvoke() calls.
    LangGraph API bypasses the model node's middleware chain entirely.
    File extraction is handled by the frontend + /api/v2/extract-pdf-text endpoint.
    """

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> Any:
        if not request.messages:
            return await handler(request)

        modified = False
        new_messages = []
        for msg in request.messages:
            if isinstance(msg, HumanMessage):
                file_blocks = _extract_file_blocks(msg.content)
                if file_blocks:
                    new_msg = self._process_file_message(msg, file_blocks)
                    new_messages.append(new_msg)
                    modified = True
                    continue
            new_messages.append(msg)

        if not modified:
            return await handler(request)

        request = request.override(messages=new_messages)
        return await handler(request)

    def _process_file_message(
        self, msg: HumanMessage, all_files: list[tuple[bytes, str, str]]
    ) -> HumanMessage:
        """Extract file content and return a new HumanMessage with text only."""
        file_contents: list[tuple[str, str, str, str]] = []
        for file_bytes, filename, mime_type in all_files:
            unique_name = f"{uuid.uuid4().hex[:8]}_{Path(filename).name}"
            file_path = _UPLOAD_DIR / unique_name

            try:
                file_path.write_bytes(file_bytes)
                logger.info("[PDFContextMiddleware] 文件已保存: %s", file_path)
            except Exception as e:
                logger.warning("[PDFContextMiddleware] 文件保存失败: %s", e)

            type_hint = "Markdown" if mime_type == "text/markdown" else "PDF"
            text = _extract_text_from_bytes(file_bytes, filename, mime_type)

            if text:
                if len(text) > _MAX_CONTENT_CHARS:
                    text = text[:_MAX_CONTENT_CHARS] + f"\n\n[... 文件内容已截断，原始长度 {len(text)} 字符 ...]"
                file_contents.append((filename, text, str(file_path), type_hint))
                logger.info("[PDFContextMiddleware] 文件内容已提取: %s (%d chars)", filename, len(text))
            else:
                file_contents.append((filename, f"[无法提取文件内容，文件已保存至 {file_path}]", str(file_path), type_hint))
                logger.warning("[PDFContextMiddleware] 无法提取文件内容: %s", filename)

        if not file_contents:
            return msg

        logger.info(
            "[PDFContextMiddleware] Processed %d/%d files: %s",
            len(file_contents), len(all_files),
            [name for name, _, _, _ in file_contents],
        )

        content_sections: list[str] = []
        for filename, text, saved_path, type_hint in file_contents:
            section = (
                f"### 文件: {filename} ({type_hint})\n"
                f"（文件已保存至 {saved_path}）\n\n"
                f"{text}"
            )
            content_sections.append(section)

        all_content = "\n\n---\n\n".join(content_sections)
        prompt_text = (
            f"\n\n[系统提示] 用户上传了 {len(file_contents)} 个文件，"
            f"以下为各文件的完整内容。请基于所有文件内容进行分析：\n\n{all_content}"
        )

        original_content = msg.content
        if isinstance(original_content, str):
            new_content = original_content + prompt_text
        elif isinstance(original_content, list):
            filtered = [b for b in original_content if not (isinstance(b, dict) and b.get("type") == "file")]
            new_content = filtered + [{"type": "text", "text": prompt_text}]
        else:
            new_content = str(original_content) + prompt_text

        return HumanMessage(content=new_content, additional_kwargs=msg.additional_kwargs)


# Backward compatibility
FileContextMiddleware = PDFContextMiddleware
