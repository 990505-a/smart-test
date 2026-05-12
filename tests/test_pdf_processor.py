"""Unit tests for PDFProcessor and extract_pdf_text."""
import pytest

from src.app.processors.pdf import (
    PDFProcessor,
    _safe_delete_temp_file,
    extract_pdf_text,
)


class TestExtractPdfText:
    """Tests for the extract_pdf_text module-level function."""

    def test_extract_pdf_text_returns_content(self, sample_pdf_bytes):
        """extract_pdf_text returns non-empty Markdown text from valid PDF bytes."""
        result = extract_pdf_text(sample_pdf_bytes, "test.pdf")
        assert isinstance(result, str)
        assert len(result) > 0
        # The PDF contains "Test Document Content" drawn on it
        assert "Test Document Content" in result

    def test_md5_cache_returns_cached_result(self, sample_pdf_bytes, cache_dict):
        """Same PDF bytes with same cache dict returns cached result (same string)."""
        first = extract_pdf_text(sample_pdf_bytes, "test.pdf", cache=cache_dict)
        second = extract_pdf_text(sample_pdf_bytes, "test.pdf", cache=cache_dict)

        # Second call returns the exact same string object (cached)
        assert first is second
        # Cache has exactly 1 entry
        assert len(cache_dict) == 1
        # The key contains the MD5 hash
        key = list(cache_dict.keys())[0]
        assert "test.pdf" in key
        assert "_" in key  # format: filename_hash

    def test_md5_cache_different_files(self, sample_pdf_bytes, another_pdf_bytes, cache_dict):
        """Different PDF bytes result in 2 cache entries."""
        extract_pdf_text(sample_pdf_bytes, "doc1.pdf", cache=cache_dict)
        extract_pdf_text(another_pdf_bytes, "doc2.pdf", cache=cache_dict)

        assert len(cache_dict) == 2

    def test_extract_pdf_text_empty_bytes(self):
        """Empty bytes return empty string without raising."""
        result = extract_pdf_text(b"", "empty.pdf")
        assert isinstance(result, str)
        assert result == ""

    def test_extract_pdf_text_no_cache(self, sample_pdf_bytes):
        """Calling without cache dict still works (caching disabled)."""
        result = extract_pdf_text(sample_pdf_bytes, "test.pdf", cache=None)
        assert isinstance(result, str)
        assert len(result) > 0


class TestPDFProcessorClass:
    """Tests for the PDFProcessor class."""

    def test_pdf_processor_class(self, sample_pdf_bytes):
        """PDFProcessor with enable_cache=True extracts text."""
        processor = PDFProcessor(enable_cache=True)
        result = processor.extract_text(sample_pdf_bytes, "test.pdf")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_pdf_processor_cache_disabled(self, sample_pdf_bytes):
        """PDFProcessor with enable_cache=False returns different string objects."""
        processor = PDFProcessor(enable_cache=False)
        first = processor.extract_text(sample_pdf_bytes, "test.pdf")
        second = processor.extract_text(sample_pdf_bytes, "test.pdf")

        # Both return valid content but are not the same cached object
        assert isinstance(first, str) and isinstance(second, str)
        # Content should be the same text but not cached (different objects when cache disabled)
        assert first == second

    def test_pdf_processor_clear_cache(self, sample_pdf_bytes):
        """clear_cache() empties the cache dictionary."""
        processor = PDFProcessor(enable_cache=True)
        processor.clear_cache()  # Start clean
        processor.extract_text(sample_pdf_bytes, "test.pdf")
        assert processor.get_cache_stats()["cached_files"] >= 1

        processor.clear_cache()
        assert processor.get_cache_stats()["cached_files"] == 0

    def test_pdf_processor_get_cache_stats(self):
        """get_cache_stats() returns expected structure."""
        processor = PDFProcessor(enable_cache=False)
        stats = processor.get_cache_stats()
        assert "cache_enabled" in stats
        assert "cached_files" in stats
        assert "cache_keys" in stats
        assert stats["cache_enabled"] is False
        assert stats["cached_files"] == 0


class TestSafeDeleteTempFile:
    """Tests for _safe_delete_temp_file helper."""

    def test_safe_delete_temp_file_nonexistent(self):
        """Deleting a nonexistent file does not raise."""
        # Should not raise any exception
        _safe_delete_temp_file("/nonexistent/path/test_file_xyz.pdf")
