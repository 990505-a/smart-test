"""PDF document processor with MD5 caching.

Per D-07: Uses PyMuPDF4LLM(mode="page", extract_images=True) to convert PDF to Markdown.
Per D-08: MD5 hash caching avoids re-parsing the same document.
"""
import hashlib
import logging
import os
import tempfile
import time
from typing import Optional

from langchain_core.tools import tool
from langchain_pymupdf4llm import PyMuPDF4LLMLoader

logger = logging.getLogger(__name__)

# Module-level cache dict for parsed PDF content
_pdf_cache: dict[str, str] = {}


def _safe_delete_temp_file(file_path: str, max_retries: int = 3, delay: float = 0.1) -> None:
    """Safely delete temp file, handling Windows file locking. Retry up to max_retries times."""
    if not os.path.exists(file_path):
        return
    for attempt in range(max_retries):
        try:
            os.unlink(file_path)
            logger.debug("Temp file deleted: %s", file_path)
            return
        except PermissionError:
            if attempt < max_retries - 1:
                logger.debug(
                    "Delete failed (attempt %d/%d), retrying: %s",
                    attempt + 1, max_retries, file_path,
                )
                time.sleep(delay)
            else:
                logger.warning(
                    "Cannot delete temp file after %d retries: %s",
                    max_retries, file_path,
                )
        except Exception as e:
            logger.warning("Error deleting temp file: %s", e)
            break


def _get_cache_key(data: bytes, filename: str) -> str:
    """Generate cache key from PDF binary data MD5 hash."""
    return f"{filename}_{hashlib.md5(data).hexdigest()}"


def extract_pdf_text(
    pdf_data: bytes,
    filename: str = "unknown.pdf",
    cache: Optional[dict] = None,
    extract_images: bool = False,
    images_parser=None,
) -> str:
    """Extract text from PDF bytes using PyMuPDF4LLM.

    Args:
        pdf_data: Raw PDF file bytes.
        filename: Original filename for cache keying.
        cache: Optional dict for caching results. Pass None to disable caching.
        extract_images: Whether to extract images (requires images_parser if True).
        images_parser: Optional image parser for multimodal extraction.

    Returns:
        Extracted Markdown text content.
    """
    if not pdf_data:
        return ""

    cache_key = _get_cache_key(pdf_data, filename)
    if cache is not None and cache_key in cache:
        logger.info("PDF cache hit: %s", filename)
        return cache[cache_key]

    temp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    try:
        temp_file.write(pdf_data)
        temp_file.flush()
        os.fsync(temp_file.fileno())
        temp_path = temp_file.name
    finally:
        temp_file.close()

    try:
        loader_kwargs = {
            "mode": "page",            # D-07
        }
        # Only enable image extraction when a parser is provided (multimodal mode)
        if extract_images and images_parser is not None:
            loader_kwargs["extract_images"] = True
            loader_kwargs["images_parser"] = images_parser
        else:
            loader_kwargs["extract_images"] = False

        loader = PyMuPDF4LLMLoader(file_path=temp_path, **loader_kwargs)
        documents = loader.load()
        text = "\n\n".join(doc.page_content for doc in documents) if documents else ""

        if cache is not None:
            cache[cache_key] = text
            logger.info("PDF content cached: %s (%d chars)", filename, len(text))

        return text
    except Exception as e:
        logger.error("PDF text extraction failed: %s", e)
        return f"PDF processing error: {e}"
    finally:
        _safe_delete_temp_file(temp_path)


class PDFProcessor:
    """PDF processor class wrapping extract_pdf_text with optional caching."""

    def __init__(self, enable_cache: bool = True):
        self.enable_cache = enable_cache
        self.cache = _pdf_cache if enable_cache else {}

    def extract_text(self, pdf_data: bytes, filename: str = "unknown.pdf") -> str:
        """Extract text from PDF bytes, using cache if enabled."""
        return extract_pdf_text(pdf_data, filename, self.cache if self.enable_cache else None)

    def clear_cache(self):
        """Clear the cache dictionary."""
        if self.enable_cache:
            self.cache.clear()

    def get_cache_stats(self) -> dict:
        """Return cache statistics."""
        return {
            "cache_enabled": self.enable_cache,
            "cached_files": len(self.cache) if self.enable_cache else 0,
            "cache_keys": list(self.cache.keys()) if self.enable_cache else [],
        }


@tool
def extract_pdf_text_from_file(file_path: str) -> str:
    """从PDF文件路径中提取文本，使用模块级缓存避免重复解析。

    Args:
        file_path: PDF 文件的绝对路径或相对路径

    Returns:
        提取的文本内容
    """
    if not os.path.isfile(file_path):
        logger.error("PDF文件不存在: %s", file_path)
        return f"PDF文件不存在: {file_path}"

    try:
        with open(file_path, "rb") as f:
            pdf_data = f.read()
    except OSError as e:
        logger.error("读取PDF文件失败: %s", e)
        return f"读取PDF文件失败: {e}"

    filename = os.path.basename(file_path)
    return extract_pdf_text(pdf_data, filename, _pdf_cache)
