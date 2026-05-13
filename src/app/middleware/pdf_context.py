"""File context injection middleware (FileContextMiddleware).

Extracts files (PDF, image, Excel) from the last HumanMessage's
additional_kwargs.attachments and content blocks, parses the content,
and injects it into the agent's system prompt.

Design notes (v5):
    - thread_id is obtained via langgraph.config.get_config() from the async context.
    - The original SYSTEM_PROMPT is passed via the constructor (original_system_prompt param).
    - Internal state: thread_id -> doc_text dict for per-session document management.
    - Each request scans only the last user message for file attachments.
    - MD5 hash dedup prevents re-parsing the same document in the same thread.
    - Supports PDF, image (png/jpg/jpeg/gif/webp), and Excel (xlsx/xls) file types.

    v5 key change (multi-file dispatch):
    - Renamed from PDFContextMiddleware to FileContextMiddleware.
    - Dispatches to PDFProcessor, ImageProcessor, or ExcelProcessor by MIME type.
    - Multiple files in a single message are all processed and concatenated.
    - Backward-compatible alias: PDFContextMiddleware = FileContextMiddleware.

    v4 key change (compatible with SkillsMiddleware):
    - _build_system_message() accepts current_system_message parameter.
    - File injection uses current request.system_message as base (already contains
      Skills content), not hardcoded _original_system_content, preserving
      SkillsMiddleware-injected Skills list.
    - awrap_model_call() passes request.system_message to _build_system_message().

    Middleware execution order (onion model, FileContextMiddleware registered last = innermost):
      |-- SkillsMiddleware     -> append skills to system_message
      |   |-- dynamic_model    -> select model
      |   |   |-- FileContextMiddleware -> use current system_message (with Skills) as base, append files
      |   |   |-- LLM
"""

from __future__ import annotations

import base64
import hashlib
import logging
from typing import Any, Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.middleware.types import ResponseT
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.typing import ContextT

from src.app.processors.excel import ExcelProcessor
from src.app.processors.image import ImageProcessor
from src.app.processors.pdf import PDFProcessor

logger = logging.getLogger(__name__)

_DOCUMENT_TEMPLATE = """\
以下是用户上传的参考文档，请在回答时充分参考其内容：

<document>
{content}
</document>
"""


def _decode_base64(data: str) -> bytes:
    """Decode a base64 string to bytes, handling data URI prefix."""
    if "," in data:
        data = data.split(",", 1)[1]
    return base64.b64decode(data)


# Supported MIME types for file extraction
_PDF_MIME = "application/pdf"
_EXCEL_MIMES = frozenset({
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
})


class FileContextMiddleware(AgentMiddleware):
    """Multi-file context injection middleware with session isolation.

    Core features:
    1. original_system_prompt passed via constructor, completely independent of runtime
       request.system_message, avoiding snapshot pollution from server restarts.
    2. thread_id obtained via langgraph.config.get_config() from async context.
    3. _session_docs keyed by thread_id for per-session document state, naturally isolated.
    4. Scans only the last user message for file attachments (PDF, image, Excel).
    5. Multiple files in a single message are all processed and concatenated.
    6. Uses request.override() for immutable replacement pattern.
    """

    def __init__(
        self,
        original_system_prompt: str | list | None = None,
        enable_cache: bool = True,
        max_content_length: int = 80_000,
        api_key: str = "",
    ):
        """
        Args:
            original_system_prompt: Agent's original system prompt. If None,
                falls back to reading from request.system_message on first call.
            enable_cache: Whether to enable PDF parsing cache.
            max_content_length: Max chars for file content, truncated if exceeded.
            api_key: OpenAI API key for ImageProcessor (GPT-4o vision).
        """
        self._pdf_processor = PDFProcessor(enable_cache=enable_cache)
        self._image_processor = ImageProcessor(api_key=api_key)
        self._excel_processor = ExcelProcessor()
        self._max_content_length = max_content_length
        # Original system prompt (read-only, never modified at runtime)
        self._original_system_content: str | list | None = original_system_prompt
        # Per-session document state: thread_id -> doc_text (accumulation semantics)
        self._session_docs: dict[str, str] = {}
        # Per-session parsed file hash: cache_key -> file_md5
        # Same hash -> reuse, skip parsing; Different hash -> new file, re-parse
        self._session_file_hash: dict[str, str] = {}

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> Any:
        """Intercept LLM call, inject file document context per session.

        v5: Multi-file dispatch. Scans last user message for all supported
        file types (PDF, image, Excel), processes each via appropriate processor,
        and concatenates results into the session document store.
        """

        # Step 1: Fallback snapshot (compatibility when original_system_prompt not provided)
        if self._original_system_content is None and request.system_message is not None:
            self._original_system_content = request.system_message.content
            logger.warning(
                "FileContextMiddleware: original_system_prompt not provided, "
                "captured from first request.system_message. "
                "Recommend passing via constructor for safety."
            )

        # Step 2: Get thread_id from LangGraph async context
        thread_id = self._get_thread_id()

        # Step 3: Process all file attachments in the last user message
        files = self._extract_files_from_last_message(request)
        if files:
            for file_data, filename, mime_type in files:
                file_hash = hashlib.md5(file_data).hexdigest()
                cache_key = f"{thread_id}_{filename}"
                if self._session_file_hash.get(cache_key) == file_hash:
                    logger.debug(
                        "FileContextMiddleware: session %s file %s unchanged (hash=%s), skip re-parsing",
                        thread_id, filename, file_hash,
                    )
                    continue
                logger.info("FileContextMiddleware: new file detected: %s (%s), extracting text...", filename, mime_type)
                text = self._process_file(file_data, filename, mime_type)
                if text:
                    existing = self._session_docs.get(thread_id, "")
                    self._session_docs[thread_id] = (existing + "\n\n" + text) if existing else text
                    self._session_file_hash[cache_key] = file_hash
                    logger.info(
                        "FileContextMiddleware: session %s document updated: %s, length: %d chars",
                        thread_id, filename, len(text),
                    )

        # Step 4: Inject document into system_message if present for this session
        # Key fix: use request.system_message (contains Skills) as base,
        # not _original_system_content, to preserve SkillsMiddleware content.
        current_doc = self._session_docs.get(thread_id)
        if current_doc:
            current_system_msg = request.system_message
            request = request.override(
                system_message=self._build_system_message(current_doc, current_system_msg)
            )
            logger.info(
                "FileContextMiddleware: session %s system_message injected with file context (Skills preserved)",
                thread_id,
            )
        else:
            logger.debug(
                "FileContextMiddleware: session %s no document, passing through",
                thread_id,
            )

        return await handler(request)

    # -------------------------------------------------------------------------
    # Internal helper methods
    # -------------------------------------------------------------------------

    def _get_thread_id(self) -> str:
        """Get thread_id from LangGraph async context for session differentiation.

        Path: get_config()["configurable"]["thread_id"]
        Falls back to "__default__" for single-user local debugging.
        """
        try:
            from langgraph.config import get_config
            config = get_config()
            tid = (
                config.get("metadata", {}).get("thread_id")
                or config.get("configurable", {}).get("thread_id")
            )
            if tid:
                return str(tid)
        except Exception:
            pass
        return "__default__"

    def _extract_files_from_last_message(
        self, request: ModelRequest
    ) -> list[tuple[bytes, str, str]]:
        """Extract all supported file attachments from the last user message.

        Scans both additional_kwargs.attachments and content blocks for:
        - PDF files (application/pdf)
        - Image files (image/*)
        - Excel files (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,
                       application/vnd.ms-excel)

        Returns:
            List of (file_bytes, filename, mime_type) tuples.
        """
        if not request.messages:
            return []

        last_msg = request.messages[-1]
        if not isinstance(last_msg, HumanMessage):
            return []

        results: list[tuple[bytes, str, str]] = []

        # Source 1: attachments in additional_kwargs
        attachments = last_msg.additional_kwargs.get("attachments", [])
        if isinstance(attachments, list):
            for att in attachments:
                if not isinstance(att, dict):
                    continue
                mime_type = att.get("mimeType", "").lower()

                # Check if it's a supported MIME type
                if mime_type not in (
                    _PDF_MIME,
                    *_EXCEL_MIMES,
                ) and not mime_type.startswith("image/"):
                    continue

                data = att.get("data")
                if not data or not isinstance(data, str):
                    continue

                try:
                    file_bytes = _decode_base64(data)
                    filename = att.get("metadata", {}).get("filename", f"file.{mime_type.split('/')[-1]}")
                    results.append((file_bytes, filename, mime_type))
                except Exception as e:
                    logger.warning("FileContextMiddleware: file decode failed: %s", e)
                    continue

        # Source 2: image_url content blocks (inline images)
        content = last_msg.content
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") != "image_url":
                    continue
                url = block.get("image_url", {}).get("url", "")
                if not url:
                    continue

                # Parse data URI: data:image/png;base64,<base64data>
                if url.startswith("data:image/"):
                    try:
                        # Extract MIME type from data URI prefix
                        header, b64_data = url.split(",", 1)
                        # header: data:image/png;base64
                        mime_part = header.split(":")[1].split(";")[0]  # image/png
                        file_bytes = base64.b64decode(b64_data)
                        ext = mime_part.split("/")[1]  # png
                        filename = f"inline_image.{ext}"
                        results.append((file_bytes, filename, mime_part))
                    except Exception as e:
                        logger.warning("FileContextMiddleware: image_url decode failed: %s", e)
                        continue

        return results

    def _process_file(self, data: bytes, filename: str, mime_type: str) -> str:
        """Dispatch file to the appropriate processor by MIME type.

        Args:
            data: Raw file bytes.
            filename: Original filename.
            mime_type: MIME type of the file.

        Returns:
            Extracted text content, or empty string for unsupported types.
        """
        if mime_type == _PDF_MIME:
            return self._pdf_processor.extract_text(data, filename)
        elif mime_type.startswith("image/"):
            return self._image_processor.extract_text(data, filename)
        elif mime_type in _EXCEL_MIMES:
            return self._excel_processor.extract_text(data, filename)
        else:
            logger.warning("FileContextMiddleware: unsupported MIME type: %s", mime_type)
            return ""

    def _build_system_message(
        self,
        doc_text: str,
        current_system_message: SystemMessage | None = None,
    ) -> SystemMessage:
        """Build new SystemMessage with file block appended.

        v4 key change:
        Uses current_system_message.content as base (contains Skills injection),
        falls back to _original_system_content only when None.
        This preserves all SkillsMiddleware-appended content.
        """
        if len(doc_text) > self._max_content_length:
            doc_text = doc_text[:self._max_content_length] + "\n\n[Document content truncated...]"

        doc_block_text = _DOCUMENT_TEMPLATE.format(content=doc_text)

        # Use current request's system_message as base (preserves Skills content)
        if current_system_message is not None:
            base_content = current_system_message.content
        else:
            base_content = self._original_system_content

        if isinstance(base_content, str):
            new_content: str | list = base_content + "\n\n" + doc_block_text
        elif isinstance(base_content, list):
            new_content = list(base_content) + [{"type": "text", "text": doc_block_text}]
        else:
            new_content = doc_block_text

        return SystemMessage(content=new_content)

    def clear_session(self, thread_id: str) -> None:
        """Clear document state for a specific session (e.g., user clears context)."""
        removed = self._session_docs.pop(thread_id, None)
        # Clean up file hashes for this thread
        keys_to_remove = [k for k in self._session_file_hash if k.startswith(f"{thread_id}_")]
        for k in keys_to_remove:
            self._session_file_hash.pop(k, None)
        if removed is not None:
            logger.info("FileContextMiddleware: session %s document state cleared", thread_id)

    def get_session_stats(self) -> dict:
        """Get document state statistics for all active sessions."""
        return {
            "active_sessions": len(self._session_docs),
            "session_ids": list(self._session_docs.keys()),
            "doc_lengths": {tid: len(text) for tid, text in self._session_docs.items()},
        }


# Backward compatibility: PDFContextMiddleware is now FileContextMiddleware
PDFContextMiddleware = FileContextMiddleware
