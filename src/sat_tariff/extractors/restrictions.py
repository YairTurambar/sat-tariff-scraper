"""Restrictions extractor."""

from __future__ import annotations

from .common import ExtractionResult, parse_html, table_to_dicts
from ..models import RestrictionRecord



def parse_restrictions(html: str) -> ExtractionResult[RestrictionRecord]:
    soup = parse_html(html)
    rows: list[RestrictionRecord] = []
    for table in soup.find_all("table"):
        dict_rows = table_to_dicts(table)
        if not dict_rows:
            continue
        if not {"Código", "Descripción"}.issubset(dict_rows[0]):
            continue
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
