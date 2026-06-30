"""
Report generation service.
Moved from app/utils.py — single responsibility: produce PDF and Excel reports.
"""
from app.utils import (
    generate_pdf_report,
    generate_inline_pdf,
    generate_excel_report,
    generate_code_analysis_pdf,
)

__all__ = [
    'generate_pdf_report',
    'generate_inline_pdf',
    'generate_excel_report',
    'generate_code_analysis_pdf',
]
