"""Workbook style helpers."""

from __future__ import annotations

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

HEADER_FILL = PatternFill("solid", fgColor="4472C4")
HEADER_FONT = Font(color="FFFFFF", bold=True)
THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)



def style_headers(worksheet, header_rows: int) -> None:
    for row_index in range(1, header_rows + 1):
        worksheet.row_dimensions[row_index].height = 22
        for cell in worksheet[row_index]:
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.border = THIN_BORDER
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)



def style_data_cells(worksheet, start_row: int) -> None:
    for row in worksheet.iter_rows(min_row=start_row):
        for cell in row:
            cell.border = THIN_BORDER
            cell.alignment = Alignment(vertical="top", wrap_text=True)



def autosize_columns(worksheet) -> None:
    for index in range(1, worksheet.max_column + 1):
        width = max(len(str(worksheet.cell(row=row, column=index).value or "")) for row in range(1, worksheet.max_row + 1))
        worksheet.column_dimensions[get_column_letter(index)].width = min(max(width + 2, 12), 60)
