"""Processor-level tests (Excel) for the file-context pipeline.

Middleware-level dispatch/extraction behavior is covered in
test_pdf_middleware.py against the current content-array implementation.
"""
import io

import pytest


class TestExcelProcessor:
    """ExcelProcessor with real openpyxl data."""

    def test_excel_processor_extracts_markdown(self, sample_excel_bytes):
        """ExcelProcessor converts sample Excel to Markdown table."""
        from src.app.processors.excel import ExcelProcessor
        processor = ExcelProcessor()
        result = processor.extract_text(sample_excel_bytes, "test.xlsx")

        assert "| Name | Value | Status |" in result
        assert "| item1 | 100 | active |" in result
        assert "| item2 | 200 | inactive |" in result
        assert "### Sheet: TestSheet" in result

    def test_excel_processor_empty_input(self):
        """Empty bytes returns empty string."""
        from src.app.processors.excel import ExcelProcessor
        processor = ExcelProcessor()
        result = processor.extract_text(b"", "empty.xlsx")

        assert result == ""

    def test_excel_processor_multi_sheet(self):
        """Workbook with 2 sheets contains both sheet headings."""
        from openpyxl import Workbook

        wb = Workbook()
        ws1 = wb.active
        ws1.title = "Sheet1"
        ws1.append(["A", "B"])
        ws1.append(["1", "2"])

        ws2 = wb.create_sheet("Sheet2")
        ws2.append(["X", "Y"])
        ws2.append(["10", "20"])

        buf = io.BytesIO()
        wb.save(buf)

        from src.app.processors.excel import ExcelProcessor
        processor = ExcelProcessor()
        result = processor.extract_text(buf.getvalue(), "multi.xlsx")

        assert "### Sheet: Sheet1" in result
        assert "### Sheet: Sheet2" in result
