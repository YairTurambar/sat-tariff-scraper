from pathlib import Path
import uuid

from openpyxl import load_workbook

from sat_tariff.config import AppConfig
from sat_tariff.exporters.layouts import FORBIDDEN_EXPORT_COLUMNS
from sat_tariff.exporters.excel import export_workbook
from sat_tariff.storage import Storage



def make_paths():
    suffix = uuid.uuid4().hex
    db_path = Path("data") / f"export-test-{suffix}.sqlite3"
    xlsx_path = Path("data") / f"export-test-{suffix}.xlsx"
    for path in (db_path, xlsx_path):
        path.unlink(missing_ok=True)
    return db_path, xlsx_path



def test_exporter_builds_expected_workbook_structure():
    db_path, xlsx_path = make_paths()
    storage = Storage(db_path)
    try:
        storage.upsert_code("9999000001", "9999000001", last_error=None)
        storage.save_section_rows(
            "9999000001",
            "rights",
            [
                {
                    "agreement_name": "TRATAMIENTO GENERAL",
                    "code": "DAI",
                    "description": "General",
                    "additional_code": "AD1",
                    "value": "5%",
                    "quota_code": "CQ1",
                },
                {
                    "agreement_name": "Tratado de Libre Comercio - MX",
                    "code": "DAI",
                    "description": "Preferencial",
                    "additional_code": "AD1",
                    "value": "0%",
                    "quota_code": "CQ1",
                },
            ],
            section_status="ok",
        )
        storage.save_section_rows(
            "9999000001",
            "nomenclature",
            [
                {
                    "record_type": "unit",
                    "section": "Sección I",
                    "chapter": "Capítulo 01",
                    "effective_from_raw": "01/01/2024",
                    "effective_to_raw": "31/12/2024",
                    "additional_codes_text": "No se han encontrado códigos adicionales asociados al inciso consultado",
                    "unit_code": "KGM",
                    "unit_description": "Kilogramo",
                }
            ],
            section_status="ok",
        )
        storage.save_section_rows(
            "9999000001",
            "restrictions",
            [{"code": "R1", "description": "Licencia", "additional_code": "AD2", "value": "Sí", "quota_code": "CQ2"}],
            section_status="ok",
        )
        storage.save_section_rows(
            "9999000001",
            "quotas",
            [{"message": "No se han encontrado cuotas/contingentes para el inciso consultado"}],
            section_status="no_quotas",
        )
        bundles = storage.load_all_for_export()
    finally:
        storage.close()

    config = AppConfig(sqlite_db=db_path, output_xlsx=xlsx_path, backup_output=False)
    path = export_workbook(bundles, config)
    workbook = load_workbook(path)
    assert workbook.sheetnames == ["Derechos e impuestos", "Nomenclatura", "Restricciones", "Cuotas"]
    assert "Sheet" not in workbook.sheetnames

    rights = workbook["Derechos e impuestos"]
    nomenclature = workbook["Nomenclatura"]
    restrictions = workbook["Restricciones"]
    quotas = workbook["Cuotas"]

    assert rights["A1"].value == "HS_Code"
    assert rights["A1"].fill.fgColor.rgb[-6:] == "4472C4"
    assert rights["A1"].font.bold is True
    assert rights["A1"].font.color.rgb[-6:] == "FFFFFF"
    assert rights.row_dimensions[1].height == 22
    assert rights.freeze_panes == "A3"
    assert rights["A3"].number_format == "@"
    rights_merges = {str(cell_range) for cell_range in rights.merged_cells.ranges}
    assert "A1:A2" in rights_merges  # HS_Code spans both header rows
    assert "G1:G2" in rights_merges  # Código adicional spans both header rows
    rights_row1 = [cell.value for cell in rights[1]]
    rights_row2 = [cell.value for cell in rights[2]]
    assert rights_row1[4] == "TRATAMIENTO GENERAL"
    assert rights_row1[5] == "Tratado de Libre Comercio - MX"
    assert rights_row2[4:6] == ["DAI", "DAI"]

    assert any(str(cell_range) == "I1:J1" for cell_range in nomenclature.merged_cells.ranges)
    assert nomenclature.freeze_panes == "A3"
    assert nomenclature["A3"].number_format == "@"

    assert restrictions["A1"].value == "HS_Code"
    assert quotas["D1"].value == "TRATAMIENTO GENERAL"
    for sheet in (restrictions, quotas):
        headers = [cell.value for cell in sheet[1] if cell.value]
        assert FORBIDDEN_EXPORT_COLUMNS.isdisjoint(headers)
    rights_headers = [value for value in rights_row1 + rights_row2 if value]
    assert FORBIDDEN_EXPORT_COLUMNS.isdisjoint(rights_headers)
    nomenclature_headers = [
        nomenclature.cell(row=2, column=index).value or nomenclature.cell(row=1, column=index).value
        for index in range(1, nomenclature.max_column + 1)
    ]
    assert FORBIDDEN_EXPORT_COLUMNS.isdisjoint({header for header in nomenclature_headers if header})

    workbook.close()
    path.unlink(missing_ok=True)
    db_path.unlink(missing_ok=True)


def test_rights_sheet_merges_multiple_codes_under_one_agreement_group(tmp_path):
    """TRATAMIENTO GENERAL (and other agreements) should merge across every
    duty/tax code column that belongs to them, not just a single column."""
    import sys

    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from sample_workbook import export_sample_workbook

    path = export_sample_workbook(tmp_path / "sample.xlsx")
    workbook = load_workbook(path)
    rights = workbook["Derechos e impuestos"]

    merges = {str(cell_range) for cell_range in rights.merged_cells.ranges}
    assert "E1:F1" in merges  # TRATAMIENTO GENERAL spans DAI + IVA columns
    row1 = [cell.value for cell in rights[1]]
    row2 = [cell.value for cell in rights[2]]
    assert row1[4] == "TRATAMIENTO GENERAL"
    assert row2[4:6] == ["DAI", "IVA"]
    assert row1[6] == "Tratado de Libre Comercio - MX"
    assert row2[6] == "DAI"

    workbook.close()
