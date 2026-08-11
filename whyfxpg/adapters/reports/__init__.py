"""
Report renderer adapters: concrete implementations of the ReportRenderer port.
"""
from whyfxpg.adapters.reports.excel_report_adapter import ExcelReportRenderer
from whyfxpg.adapters.reports.in_memory_report_adapter import InMemoryReportRenderer
from whyfxpg.adapters.reports.word_report_adapter import WordReportRenderer

__all__ = ["ExcelReportRenderer", "InMemoryReportRenderer", "WordReportRenderer"]
