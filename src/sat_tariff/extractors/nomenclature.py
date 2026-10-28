"""Nomenclature extractor."""

from __future__ import annotations

from .common import ExtractionResult, ascii_upper, extract_labeled_value, extract_text_after_label, find_table_after_label, parse_date_attempt, parse_html, table_to_dicts, table_to_labeled_dicts
from ..models import NomenclatureRecord

BLOCK_LABELS = (
    "Código de Mercancías",
    "Códigos adicionales",
    "Unidades de medida",
    "Clasificadores estadísticos",
    "Descripciones mínimas",
    "Criterios de Clasificación",
)


def _base_record(
    record_type: str,
    section: str,
    chapter: str,
    from_raw: str,
    to_raw: str,
    additional_text: str,
    *,
    source_status: str,
) -> dict[str, str | None]:
    return {
        "record_type": record_type,
        "section": section,
        "chapter": chapter,
        "effective_from_raw": from_raw,
        "effective_from_normalized": parse_date_attempt(from_raw),
        "effective_to_raw": to_raw,
        "effective_to_normalized": parse_date_attempt(to_raw),
        "additional_codes_text": additional_text,
        "source_status": source_status,
    }


def parse_nomenclature(html: str) -> ExtractionResult[NomenclatureRecord]:
    soup = parse_html(html)
    page_text = ascii_upper(soup.get_text(" ", strip=True))
    if ("SESION" in page_text and ("EXPIR" in page_text or "CADUC" in page_text)) or "CAPTCHA" in page_text:
        return ExtractionResult(rows=[], status="extraction_error", message="Session expired or manual CAPTCHA required")
    if soup.find(["h1", "title"], string=lambda text: bool(text and "ERROR" in ascii_upper(text))):
        return ExtractionResult(rows=[], status="extraction_error", message="SAT error page")
    section = extract_labeled_value(soup, "Sección")
    chapter = extract_labeled_value(soup, "Capítulo:")
    from_raw = extract_labeled_value(soup, "Fecha inicio de vigencia:")
    to_raw = extract_labeled_value(soup, "Fecha fin de vigencia:")
    additional_table = find_table_after_label(soup, "Códigos adicionales", BLOCK_LABELS)
    if additional_table is not None:
        additional_chunks = []
        for row in table_to_dicts(additional_table):
            additional_chunks.append(" | ".join(value for value in row.values() if value))
        additional_text = "\n".join(chunk for chunk in additional_chunks if chunk)
    else:
        additional_text = extract_text_after_label(soup, "Códigos adicionales", BLOCK_LABELS)

    rows: list[NomenclatureRecord] = []
    goods_table = find_table_after_label(soup, "Código de Mercancías", BLOCK_LABELS)
    if goods_table is not None:
        for row in table_to_labeled_dicts(goods_table, ("Código", "Descripción")):
            rows.append(
                NomenclatureRecord(
                    **_base_record("goods", section, chapter, from_raw, to_raw, additional_text, source_status="ok"),
                    unit_code="",
                    unit_description="",
                    code=row.get("CODIGO", ""),
                    description=row.get("DESCRIPCION", ""),
                )
            )

    units_table = find_table_after_label(soup, "Unidades de medida", BLOCK_LABELS)
    if units_table is not None:
        for row in table_to_labeled_dicts(units_table, ("Código", "Descripción")):
            rows.append(
                NomenclatureRecord(
                    **_base_record("unit", section, chapter, from_raw, to_raw, additional_text, source_status="ok"),
                    unit_code=row.get("CODIGO", ""),
                    unit_description=row.get("DESCRIPCION", ""),
                )
            )

    for label in (
        "Clasificadores estadísticos",
        "Descripciones mínimas",
        "Criterios de Clasificación",
    ):
        content = extract_text_after_label(soup, label, BLOCK_LABELS)
        if content:
            rows.append(
                NomenclatureRecord(
                    **_base_record(label, section, chapter, from_raw, to_raw, additional_text, source_status="ok"),
                    unit_code="",
                    unit_description="",
                    content=content,
                )
            )

    if rows:
        return ExtractionResult(rows=rows, status="ok")
    if any([section, chapter, from_raw, to_raw, additional_text]):
        rows.append(
            NomenclatureRecord(
                **_base_record("summary", section, chapter, from_raw, to_raw, additional_text, source_status="ok"),
                unit_code="",
                unit_description="",
            )
        )
        return ExtractionResult(rows=rows, status="ok")
    return ExtractionResult(rows=[], status="absent", message="Nomenclature section not found")
