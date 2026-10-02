"""Nomenclature extractor."""

from __future__ import annotations

from .common import ExtractionResult, extract_labeled_value, extract_text_after_label, find_table_after_label, parse_date_attempt, parse_html, table_to_dicts
from ..models import NomenclatureRecord

BLOCK_LABELS = (
    "Código de Mercancías",
    "Códigos adicionales",
    "Unidades de medida",
    "Clasificadores estadísticos",
    "Descripciones mínimas",
    "Criterios de Clasificación",
)



def parse_nomenclature(html: str) -> ExtractionResult[NomenclatureRecord]:
    soup = parse_html(html)
    section = extract_labeled_value(soup, "Sección")
    chapter = extract_labeled_value(soup, "Capítulo:")
    from_raw = extract_labeled_value(soup, "Fecha inicio de vigencia:")
    to_raw = extract_labeled_value(soup, "Fecha fin de vigencia:")
    additional_text = extract_text_after_label(soup, "Códigos adicionales", BLOCK_LABELS)

    rows: list[NomenclatureRecord] = []
    goods_table = find_table_after_label(soup, "Código de Mercancías", BLOCK_LABELS)
    if goods_table is not None:
        for row in table_to_dicts(goods_table):
            rows.append(
                NomenclatureRecord(
                    record_type="goods",
                    section=section,
                    chapter=chapter,
                    effective_from_raw=from_raw,
                    effective_from_normalized=parse_date_attempt(from_raw),
                    effective_to_raw=to_raw,
                    effective_to_normalized=parse_date_attempt(to_raw),
                    additional_codes_text=additional_text,
                    unit_code="",
                    unit_description="",
                    source_status="ok",
                    code=row.get("Código", ""),
                    description=row.get("Descripción", ""),
                )
            )

    units_table = find_table_after_label(soup, "Unidades de medida", BLOCK_LABELS)
    if units_table is not None:
        for row in table_to_dicts(units_table):
            rows.append(
                NomenclatureRecord(
                    record_type="unit",
                    section=section,
                    chapter=chapter,
                    effective_from_raw=from_raw,
                    effective_from_normalized=parse_date_attempt(from_raw),
                    effective_to_raw=to_raw,
                    effective_to_normalized=parse_date_attempt(to_raw),
                    additional_codes_text=additional_text,
                    unit_code=row.get("Código", ""),
                    unit_description=row.get("Descripción", ""),
                    source_status="ok",
                )
            )

    if rows:
        return ExtractionResult(rows=rows, status="ok")
    if any([section, chapter, from_raw, to_raw, additional_text]):
        rows.append(
            NomenclatureRecord(
                record_type="summary",
                section=section,
                chapter=chapter,
                effective_from_raw=from_raw,
                effective_from_normalized=parse_date_attempt(from_raw),
                effective_to_raw=to_raw,
                effective_to_normalized=parse_date_attempt(to_raw),
                additional_codes_text=additional_text,
                unit_code="",
                unit_description="",
                source_status="empty",
            )
        )
        return ExtractionResult(rows=rows, status="empty")
    return ExtractionResult(rows=[], status="absent", message="Nomenclature section not found")
