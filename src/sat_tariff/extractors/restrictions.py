"""Restrictions extractor."""

from __future__ import annotations

from .common import ExtractionResult, iter_standard_section_tables, parse_html
from ..models import RestrictionRecord


def parse_restrictions(html: str) -> ExtractionResult[RestrictionRecord]:
    soup = parse_html(html)
    rows: list[RestrictionRecord] = []
    for _title, dict_rows in iter_standard_section_tables(soup):
        for row in dict_rows:
            rows.append(
                RestrictionRecord(
                    code=row.get("Código", ""),
                    description=row.get("Descripción", ""),
                    additional_code=row.get("Código adicional", ""),
                    value=row.get("Valor", ""),
                    quota_code=row.get("Código de cuota", ""),
                )
            )
    if rows:
        return ExtractionResult(rows=rows, status="ok")
    return ExtractionResult(rows=[RestrictionRecord(code="", description="sin información", additional_code="", value="", quota_code="", source_status="sin_informacion")], status="sin_informacion")
