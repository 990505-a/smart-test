"""Graph node for pre-processing file blocks in HumanMessages.

Extracts PDF/Markdown content from {type: "file"} content blocks,
decodes and extracts text, and replaces them with {type: "text"} blocks.

This runs as a regular LangGraph node (not middleware), so it is guaranteed
to execute through the LangGraph API.
"""

from __future__ import annotations

import base64
import logging
import uuid
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

_UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "workspace" / "uploads"
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_SUPPORTED_MIME = {"application/pdf", "text/markdown"}
_MAX_CONTENT_CHARS = 50_000


def _decode_base64(data: str) -> bytes:
    if "," in data:
        data = data.split(",", 1)[1]
    return base64.b64decode(data)


def _extract_file_blocks(content: Any) -> list[tuple[bytes, str, str]]:
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
            logger.warning("[FilePreprocess] base64 decode failed: %s", e)
    return results


def _extract_text(file_bytes: bytes, filename: str, mime_type: str) -> str:
    if mime_type == "text/markdown":
        try:
            return file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return file_bytes.decode("gbk")
            except UnicodeDecodeError:
                return file_bytes.decode("utf-8", errors="replace")
    try:
        from app.processors.pdf import extract_pdf_text
        return extract_pdf_text(file_bytes, filename)
    except Exception as e:
        logger.error("[FilePreprocess] PDF extraction failed for %s: %s", filename, e)
        return f"[PDF extraction error: {e}]"


def preprocess_file_blocks(state: dict) -> dict:
    """Graph node: extract file content from HumanMessages and inject as text.

    Returns updated messages with file blocks replaced by text blocks.
    """
    messages = state.get("messages", [])
    modified = False
    new_messages = []

    for msg in messages:
        if not isinstance(msg, HumanMessage):
            new_messages.append(msg)
            continue

        file_blocks = _extract_file_blocks(msg.content)
        if not file_blocks:
            new_messages.append(msg)
            continue

        modified = True
        file_contents: list[tuple[str, str, str, str]] = []

        for file_bytes, filename, mime_type in file_blocks:
            unique_name = f"{uuid.uuid4().hex[:8]}_{Path(filename).name}"
            file_path = _UPLOAD_DIR / unique_name
            try:
                file_path.write_bytes(file_bytes)
                logger.info("[FilePreprocess] Saved: %s", file_path)
            except Exception as e:
                logger.warning("[FilePreprocess] Save failed: %s", e)

            type_hint = "Markdown" if mime_type == "text/markdown" else "PDF"
            text = _extract_text(file_bytes, filename, mime_type)

            if text:
                if len(text) > _MAX_CONTENT_CHARS:
                    text = text[:_MAX_CONTENT_CHARS] + f"\n\n[... truncated, original {len(text)} chars]"
                file_contents.append((filename, text, str(file_path), type_hint))
                logger.info("[FilePreprocess] Extracted: %s (%d chars)", filename, len(text))
            else:
                file_contents.append((filename, f"[Cannot extract content, saved to {file_path}]", str(file_path), type_hint))

        sections: list[str] = []
        for fn, txt, sp, th in file_contents:
            sections.append(f"### File: {fn} ({th})\n(saved: {sp})\n\n{txt}")

        all_content = "\n\n---\n\n".join(sections)
        prompt = (
            f"\n\n[System] {len(file_contents)} file(s) uploaded. "
            f"Content extracted below. Analyze ALL files:\n\n{all_content}"
        )

        original = msg.content
        if isinstance(original, str):
            new_content = original + prompt
        elif isinstance(original, list):
            filtered = [b for b in original if not (isinstance(b, dict) and b.get("type") == "file")]
            new_content = filtered + [{"type": "text", "text": prompt}]
        else:
            new_content = str(original) + prompt

        new_messages.append(HumanMessage(content=new_content, additional_kwargs=msg.additional_kwargs))

    if not modified:
        return state

    logger.info("[FilePreprocess] Processed files in %d messages", len(messages))
    return {"messages": new_messages}
