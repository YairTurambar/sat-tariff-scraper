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
    assert rights.freeze_panes == "A2"
    assert rights["A2"].number_format == "@"
    rights_headers = [cell.value for cell in rights[1]]
    assert rights_headers[4:6] == ["DAI_GENERAL", "DAI_MX"]

    assert any(str(cell_range) == "I1:J1" for cell_range in nomenclature.merged_cells.ranges)
    assert nomenclature.freeze_panes == "A3"
    assert nomenclature["A3"].number_format == "@"

    assert restrictions["A1"].value == "HS_Code"
    assert quotas["D1"].value == "TRATAMIENTO GENERAL"
    for sheet in (rights, restrictions, quotas):
        headers = [cell.value for cell in sheet[1] if cell.value]
        assert FORBIDDEN_EXPORT_COLUMNS.isdisjoint(headers)
    nomenclature_headers = [
        nomenclature.cell(row=2, column=index).value or nomenclature.cell(row=1, column=index).value
        for index in range(1, nomenclature.max_column + 1)
    ]
    assert FORBIDDEN_EXPORT_COLUMNS.isdisjoint({header for header in nomenclature_headers if header})

    workbook.close()
    path.unlink(missing_ok=True)
    db_path.unlink(missing_ok=True)
