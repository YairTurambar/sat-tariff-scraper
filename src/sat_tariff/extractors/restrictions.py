"""Restrictions extractor."""

from __future__ import annotations

from .common import ExtractionResult, iter_standard_section_tables, normalize_text, parse_html
from ..models import RestrictionRecord

NO_RESTRICTIONS_MESSAGE = (
    "No se han encontrado permisos no arancelarios u otras restricciones aplicables "
    "al inciso consultado para los parámetros de búsqueda"
)


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
    if NO_RESTRICTIONS_MESSAGE in normalize_text(soup.get_text(" ", strip=True)):
        return ExtractionResult(
            rows=[RestrictionRecord(code="", description=NO_RESTRICTIONS_MESSAGE, additional_code="", value="", quota_code="")],
            status="ok",
        )
    return ExtractionResult(rows=[RestrictionRecord(code="", description="sin información", additional_code="", value="", quota_code="", source_status="sin_informacion")], status="sin_informacion")
