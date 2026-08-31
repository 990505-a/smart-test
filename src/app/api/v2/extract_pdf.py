"""PDF text extraction and workspace upload endpoints.

Provides two endpoints:
1. /extract-pdf-text — Extract text from a base64-encoded PDF (legacy, used by middleware).
2. /upload-to-workspace — Extract text, save to agent workspace, return path reference.
   This is the preferred endpoint for LangGraph API flows where embedding full text
   in messages would cause thread state bloat.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from src.app.core.config import settings
from src.app.processors.pdf import PDFProcessor

logger = logging.getLogger(__name__)
router = APIRouter()

# Shared in-process cache (backed by processors.pdf._pdf_cache) so the same
# document is parsed only once regardless of which endpoint receives it.
_pdf_processor = PDFProcessor(enable_cache=True)


class ExtractPdfRequest(BaseModel):
    data: str  # base64 encoded PDF
    filename: str = "document.pdf"


class ExtractPdfResponse(BaseModel):
    text: str
    filename: str
    size: int
    chars: int


class UploadToWorkspaceRequest(BaseModel):
    data: str  # base64 encoded file
    filename: str
    mime_type: str = "application/pdf"
    space_id: str = "default"
    agent_name: str = "testcase"
    thread_id: str = ""  # thread-scoped upload subdirectory


class UploadToWorkspaceResponse(BaseModel):
    workspace_path: str  # Virtual absolute path for agent file tools (e.g., /uploads/abc_doc.pdf)
    full_path: str  # Absolute filesystem path
    filename: str
    size: int
    chars: int
    text_preview: str  # First 200 chars for display
    text_file_path: str = ""  # Virtual absolute path to extracted text file (e.g., /uploads/abc_doc_extracted.txt)


@router.post("/extract-pdf-text", response_model=ExtractPdfResponse)
async def extract_pdf_text_endpoint(req: ExtractPdfRequest):
    """Extract text from a base64-encoded PDF using PyMuPDF4LLM."""
    try:
        pdf_bytes = base64.b64decode(req.data)
    except Exception as e:
        return ExtractPdfResponse(
            text=f"[base64 decode error: {e}]",
            filename=req.filename,
            size=0,
            chars=0,
        )

    try:
        # Run in a worker thread — PyMuPDF4LLM parsing is CPU-bound and must
        # not block the event loop (it would freeze every other endpoint).
        text = await asyncio.to_thread(_pdf_processor.extract_text, pdf_bytes, req.filename)
    except Exception as e:
        logger.error("PDF extraction failed: %s", e)
        text = f"[PDF extraction error: {e}]"

    # Truncate if too long
    max_chars = 50_000
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n[... truncated, original {len(text)} chars]"

    return ExtractPdfResponse(
        text=text,
        filename=req.filename,
        size=len(pdf_bytes),
        chars=len(text),
    )


@router.post("/upload-to-workspace", response_model=UploadToWorkspaceResponse)
async def upload_to_workspace(req: UploadToWorkspaceRequest):
    """Extract text from a file, save both original and extracted text to workspace.

    Returns a workspace path reference that can be embedded in messages instead of
    the full text content. This prevents LangGraph thread state bloat.

    The saved files go to workspace/{space_id}/{agent_name}/uploads/{thread_id}/ and are
    accessible by the agent via its FilesystemBackend file tools.
    When thread_id is provided, files are isolated per-conversation-thread.
    """
    try:
        file_bytes = base64.b64decode(req.data)
    except Exception as e:
        return UploadToWorkspaceResponse(
            workspace_path="",
            full_path="",
            filename=req.filename,
            size=0,
            chars=0,
            text_preview=f"[base64 decode error: {e}]",
        )

    # Resolve workspace directory — thread-scoped if thread_id provided
    workspace_dir = settings.workspace_dir / req.space_id / req.agent_name
    if req.thread_id:
        uploads_dir = workspace_dir / "uploads" / req.thread_id
    else:
        uploads_dir = workspace_dir / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique filename to avoid collisions
    unique_prefix = uuid.uuid4().hex[:8]
    safe_name = req.filename.replace(" ", "_").replace("/", "_").replace("\\", "_")
    unique_filename = f"{unique_prefix}_{safe_name}"

    # Save original file
    original_path = uploads_dir / unique_filename
    original_path.write_bytes(file_bytes)
    logger.info("[upload-to-workspace] Saved original file: %s (%d bytes)", original_path, len(file_bytes))

    # Extract text for PDF/Markdown files and save alongside
    extracted_text = ""
    extraction_ok = False
    if req.mime_type == "application/pdf":
        try:
            # Worker thread + shared cache: parsing must not block the event loop.
            extracted_text = await asyncio.to_thread(
                _pdf_processor.extract_text, file_bytes, req.filename
            )
            extraction_ok = True
        except Exception as e:
            logger.error("[upload-to-workspace] PDF extraction failed: %s", e)
    elif req.mime_type == "text/markdown":
        try:
            extracted_text = file_bytes.decode("utf-8")
            extraction_ok = True
        except UnicodeDecodeError:
            extracted_text = file_bytes.decode("utf-8", errors="replace")
            extraction_ok = True

    # Save extracted text as .txt alongside original (only if extraction succeeded)
    text_file_path = ""
    if extracted_text and extraction_ok:
        text_filename = f"{unique_prefix}_{Path(safe_name).stem}_extracted.txt"
        text_path = uploads_dir / text_filename
        text_path.write_text(extracted_text, encoding="utf-8")
        if req.thread_id:
            text_file_path = f"/uploads/{req.thread_id}/{text_filename}"
        else:
            text_file_path = f"/uploads/{text_filename}"
        logger.info("[upload-to-workspace] Saved extracted text: %s (%d chars)", text_path, len(extracted_text))

    # Virtual absolute path for agent file tools (virtual_mode=True uses /-prefixed paths)
    if req.thread_id:
        workspace_rel_path = f"/uploads/{req.thread_id}/{unique_filename}"
    else:
        workspace_rel_path = f"/uploads/{unique_filename}"

    text_preview = extracted_text[:200] if extracted_text else "[No text extracted]"
    if not extraction_ok:
        text_preview = "[Text extraction failed — original file saved to workspace]"

    return UploadToWorkspaceResponse(
        workspace_path=workspace_rel_path,
        full_path=str(original_path),
        filename=req.filename,
        size=len(file_bytes),
        chars=len(extracted_text),
        text_preview=text_preview,
        text_file_path=text_file_path,
    )
