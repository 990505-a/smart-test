"""PDF context injection middleware (PDFContextMiddleware).

Extracts PDF from the last HumanMessage's additional_kwargs.attachments,
parses the content, and injects it into the agent's system prompt.

Design notes (v4):
    - thread_id is obtained via langgraph.config.get_config() from the async context.
    - The original SYSTEM_PROMPT is passed via the constructor (original_system_prompt param).
    - Internal state: thread_id -> doc_text dict for per-session document management.
    - Each request scans only the last user message for PDF attachments.
    - MD5 hash dedup prevents re-parsing the same document in the same thread.

    v4 key change (compatible with SkillsMiddleware):
    - _build_system_message() accepts current_system_message parameter.
    - PDF injection uses current request.system_message as base (already contains
      Skills content), not hardcoded _original_system_content, preserving
      SkillsMiddleware-injected Skills list.
    - awrap_model_call() passes request.system_message to _build_system_message().

    Middleware execution order (onion model, PDFContextMiddleware registered last = innermost):
      |-- SkillsMiddleware     -> append skills to system_message
      |   |-- dynamic_model    -> select model
      |   |   |-- PDFContextMiddleware -> use current system_message (with Skills) as base, append PDF
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


class PDFContextMiddleware(AgentMiddleware):
    """PDF document context injection middleware with session isolation.

    Core features:
    1. original_system_prompt passed via constructor, completely independent of runtime
       request.system_message, avoiding snapshot pollution from server restarts.
    2. thread_id obtained via langgraph.config.get_config() from async context.
    3. _session_docs keyed by thread_id for per-session document state, naturally isolated.
    4. Scans only the last user message for PDF attachments; new files replace old ones.
    5. Uses request.override() for immutable replacement pattern.
    """

    def __init__(
        self,
        original_system_prompt: str | list | None = None,
        enable_cache: bool = True,
        max_content_length: int = 80_000,
    ):
        """
        Args:
            original_system_prompt: Agent's original system prompt. If None,
                falls back to reading from request.system_message on first call.
            enable_cache: Whether to enable PDF parsing cache.
            max_content_length: Max chars for PDF content, truncated if exceeded.
        """
        self._processor = PDFProcessor(enable_cache=enable_cache)
        self._max_content_length = max_content_length
        # Original system prompt (read-only, never modified at runtime)
        self._original_system_content: str | list | None = original_system_prompt
        # Per-session document state: thread_id -> doc_text (replacement semantics)
        self._session_docs: dict[str, str] = {}
        # Per-session parsed PDF hash: thread_id -> pdf_md5
        # Same hash -> reuse _session_docs, skip parsing
        # Different hash -> new file, re-parse and overwrite
        self._session_pdf_hash: dict[str, str] = {}

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> Any:
        """Intercept LLM call, inject PDF document context per session.

        v4: Compatible with SkillsMiddleware coexistence.
        SkillsMiddleware appends skills content to system_message in before_agent().
        PDFContextMiddleware (innermost layer) receives request.system_message
        that already contains Skills content. Therefore, PDF injection uses
        current request.system_message as base, not _original_system_content.
        """

        # Step 1: Fallback snapshot (compatibility when original_system_prompt not provided)
        if self._original_system_content is None and request.system_message is not None:
            self._original_system_content = request.system_message.content
            logger.warning(
                "PDFContextMiddleware: original_system_prompt not provided, "
                "captured from first request.system_message. "
                "Recommend passing via constructor for safety."
            )

        # Step 2: Get thread_id from LangGraph async context
        thread_id = self._get_thread_id()

        # Step 3: Only process PDF attachment in the last user message
        pdf_info = self._extract_pdf_from_last_message(request)
        if pdf_info is not None:
            pdf_data, pdf_name = pdf_info
            pdf_hash = hashlib.md5(pdf_data).hexdigest()
            if self._session_pdf_hash.get(thread_id) == pdf_hash:
                logger.debug(
                    "PDFContextMiddleware: session %s PDF unchanged (hash=%s), skip re-parsing",
                    thread_id, pdf_hash,
                )
            else:
                logger.info("PDFContextMiddleware: new PDF detected: %s, extracting text...", pdf_name)
                text = self._processor.extract_text(pdf_data, pdf_name)
                if text:
                    self._session_docs[thread_id] = text
                    self._session_pdf_hash[thread_id] = pdf_hash
                    logger.info(
                        "PDFContextMiddleware: session %s document updated: %s, length: %d chars",
                        thread_id, pdf_name, len(text),
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
                "PDFContextMiddleware: session %s system_message injected with PDF (Skills preserved)",
                thread_id,
            )
        else:
            logger.debug(
                "PDFContextMiddleware: session %s no document, passing through",
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

    def _extract_pdf_from_last_message(self, request: ModelRequest) -> tuple[bytes, str] | None:
        """Extract PDF attachment from only the last user message.

        Only examines the last message to avoid triggering parsing on every
        conversation turn. Combined with hash comparison, achieves correct
        "parse on first upload only, skip on subsequent turns" semantics.
        """
        if not request.messages:
            return None

        last_msg = request.messages[-1]
        if not isinstance(last_msg, HumanMessage):
            return None

        attachments = last_msg.additional_kwargs.get("attachments", [])
        if not isinstance(attachments, list):
            return None

        for att in attachments:
            if not isinstance(att, dict):
                continue
            if att.get("mimeType", "").lower() != "application/pdf":
                continue

            data = att.get("data")
            if not data or not isinstance(data, str):
                continue

            try:
                pdf_bytes = _decode_base64(data)
                filename = att.get("metadata", {}).get("filename", "document.pdf")
                return pdf_bytes, filename
            except Exception as e:
                logger.warning("PDFContextMiddleware: PDF decode failed: %s", e)
                continue

        return None

    def _build_system_message(
        self,
        doc_text: str,
        current_system_message: SystemMessage | None = None,
    ) -> SystemMessage:
        """Build new SystemMessage with document block appended.

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
        self._session_pdf_hash.pop(thread_id, None)
        if removed is not None:
            logger.info("PDFContextMiddleware: session %s document state cleared", thread_id)

    def get_session_stats(self) -> dict:
        """Get document state statistics for all active sessions."""
        return {
            "active_sessions": len(self._session_docs),
            "session_ids": list(self._session_docs.keys()),
            "doc_lengths": {tid: len(text) for tid, text in self._session_docs.items()},
        }
