"""Build a deterministic, representative `sat_tariff` workbook from fixture data.

This module is the single source of truth for the sample dataset used both by
the automated visual-regression test (``tests/visual/test_visual_regression.py``)
and by the reproducible render/compare CLI (``scripts/compare_excel_visual.py``).
It intentionally covers the layout features called out in
``docs/excel-format-specification.md``:

- a code with several duty agreements (``TRATAMIENTO GENERAL`` plus a
  preferential agreement) in *Derechos e impuestos*
- a code with multiple ``Unidades de medida`` rows in *Nomenclatura*
- a code with an explicit restriction row and a code with no restrictions
- a code with a quota message and the exact "no quotas" message
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import uuid

from sat_tariff.config import AppConfig
from sat_tariff.exporters.excel import export_workbook
from sat_tariff.storage import Storage

SAMPLE_CODE_FULL = "9999010101"
SAMPLE_CODE_MINIMAL = "9999020202"


def _populate_storage(storage: Storage) -> None:
    storage.upsert_code(SAMPLE_CODE_FULL, SAMPLE_CODE_FULL, last_error=None)
    storage.save_section_rows(
        SAMPLE_CODE_FULL,
        "rights",
        [
            {
                "agreement_name": "TRATAMIENTO GENERAL",
                "code": "DAI",
                "description": "Derecho arancelario a la importación",
                "additional_code": "AD1",
                "value": "15%",
                "quota_code": "CQ1",
            },
            {
                "agreement_name": "TRATAMIENTO GENERAL",
                "code": "IVA",
                "description": "Impuesto al valor agregado",
                "additional_code": "AD1",
                "value": "12%",
                "quota_code": "CQ1",
            },
            {
                "agreement_name": "Tratado de Libre Comercio - MX",
                "code": "DAI",
                "description": "Derecho arancelario a la importación",
                "additional_code": "AD1",
                "value": "0%",
                "quota_code": "CQ1",
            },
            *[
                {
                    "agreement_name": f"Tratado de Libre Comercio - {suffix}",
                    "code": "DAI",
                    "description": "Derecho arancelario a la importación",
                    "additional_code": "AD1",
                    "value": "0%",
                    "quota_code": "CQ1",
                }
                for suffix in ("CL", "ADAE", "CO", "UK", "US", "PE", "TW", "DO", "CU")
            ],
        ],
        section_status="ok",
    )
    storage.save_section_rows(
        SAMPLE_CODE_FULL,
        "nomenclature",
        [
            {
                "record_type": "unit",
                "section": "Sección I - Animales vivos y productos del reino animal",
                "chapter": "Capítulo 01 - Animales vivos",
                "effective_from_raw": "01/01/2024",
                "effective_to_raw": "",
                "additional_codes_text": "No se han encontrado códigos adicionales asociados al inciso consultado",
                "unit_code": "KGM",
                "unit_description": "Kilogramo",
            },
            {
                "record_type": "unit",
                "section": "Sección I - Animales vivos y productos del reino animal",
                "chapter": "Capítulo 01 - Animales vivos",
                "effective_from_raw": "01/01/2024",
                "effective_to_raw": "",
                "additional_codes_text": "No se han encontrado códigos adicionales asociados al inciso consultado",
                "unit_code": "U",
                "unit_description": "Unidad",
            },
        ],
        section_status="ok",
    )
    storage.save_section_rows(
        SAMPLE_CODE_FULL,
        "restrictions",
        [
            {
                "code": "R1",
                "description": "Requiere licencia sanitaria previa",
                "additional_code": "AD1",
                "value": "Sí",
                "quota_code": "CQ1",
            }
        ],
        section_status="ok",
    )
    storage.save_section_rows(
        SAMPLE_CODE_FULL,
        "quotas",
        [{"message": "Cuota anual de 1,000 TM dentro del Tratado de Libre Comercio - MX"}],
        section_status="ok",
    )

    storage.upsert_code(SAMPLE_CODE_MINIMAL, SAMPLE_CODE_MINIMAL, last_error=None)
    storage.save_section_rows(
        SAMPLE_CODE_MINIMAL,
        "rights",
        [
            {
                "agreement_name": "TRATAMIENTO GENERAL",
                "code": "DAI",
                "description": "Derecho arancelario a la importación",
                "additional_code": "",
                "value": "5%",
                "quota_code": "",
            }
        ],
        section_status="ok",
    )
    storage.save_section_rows(
        SAMPLE_CODE_MINIMAL,
        "nomenclature",
        [
            {
                "record_type": "unit",
                "section": "Sección II - Productos del reino vegetal",
                "chapter": "Capítulo 07 - Hortalizas",
                "effective_from_raw": "",
                "effective_to_raw": "",
                "additional_codes_text": "No se han encontrado códigos adicionales asociados al inciso consultado",
                "unit_code": "",
                "unit_description": "",
            }
        ],
        section_status="ok",
    )
    storage.save_section_rows(SAMPLE_CODE_MINIMAL, "restrictions", [], section_status="no_data")
    storage.save_section_rows(
        SAMPLE_CODE_MINIMAL,
        "quotas",
        [{"message": "No se han encontrado cuotas/contingentes para el inciso consultado"}],
        section_status="no_quotas",
    )


def build_sample_bundles() -> list[dict]:
    """Return the in-memory bundle list produced by a throwaway SQLite store."""
    db_path = Path(tempfile.gettempdir()) / f"sat-tariff-sample-{uuid.uuid4().hex}.sqlite3"
    storage = Storage(db_path)
    try:
        _populate_storage(storage)
        bundles = storage.load_all_for_export()
    finally:
        storage.close()
        db_path.unlink(missing_ok=True)
    return bundles


def export_sample_workbook(destination: str | Path) -> Path:
    """Export the deterministic fixture dataset through the real exporter."""
    destination = Path(destination)
    bundles = build_sample_bundles()
    config = AppConfig(
        sqlite_db=destination.with_suffix(".sqlite3"),
        output_xlsx=destination,
        backup_output=False,
    )
    return export_workbook(bundles, config, output_path=destination)


if __name__ == "__main__":
    import sys

    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("artifacts/visual/sample_workbook.xlsx")
    target.parent.mkdir(parents=True, exist_ok=True)
    path = export_sample_workbook(target)
    print(f"Sample workbook written to {path}")
