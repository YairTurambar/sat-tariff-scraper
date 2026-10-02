"""Workbook structure validation."""

from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook

EXPECTED_SHEETS = ["Derechos e impuestos", "Nomenclatura", "Restricciones", "Cuotas"]


class OutputValidationError(ValueError):
    pass



def validate_workbook_structure(path: str | Path) -> None:
    workbook = load_workbook(path)
    if workbook.sheetnames != EXPECTED_SHEETS:
        raise OutputValidationError(f"Unexpected sheet order: {workbook.sheetnames}")

    nomenclature = workbook["Nomenclatura"]
    merged_ranges = {str(cell_range) for cell_range in nomenclature.merged_cells.ranges}
    if not any(cell_range.startswith("I1:J1") for cell_range in merged_ranges):
        raise OutputValidationError("Nomenclatura sheet is missing the merged 'Unidades de medida' header.")

    rights_headers = [cell.value for cell in workbook["Derechos e impuestos"][1]]
    restrictions_headers = [cell.value for cell in workbook["Restricciones"][1]]
    quotas_headers = [cell.value for cell in workbook["Cuotas"][1]]
    if rights_headers[:4] != ["HS_Code", "Status", "Overall_Status", "Código"]:
        raise OutputValidationError("Unexpected Derechos e impuestos headers.")
    if restrictions_headers[:4] != ["HS_Code", "Status", "Overall_Status", "Código"]:
        raise OutputValidationError("Unexpected Restricciones headers.")
    if quotas_headers[:4] != ["HS_Code", "Status", "Overall_Status", "TRATAMIENTO GENERAL"]:
        raise OutputValidationError("Unexpected Cuotas headers.")
