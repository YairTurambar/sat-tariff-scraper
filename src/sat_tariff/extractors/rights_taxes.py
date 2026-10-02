"""Rights and taxes extractor."""

from __future__ import annotations

from .common import STANDARD_HEADERS, ExtractionResult, infer_table_title, parse_html, table_to_dicts
from ..models import RightsTaxesRow



def parse_rights_taxes(html: str) -> ExtractionResult[RightsTaxesRow]:
    soup = parse_html(html)
    rows: list[RightsTaxesRow] = []
    for index, table in enumerate(soup.find_all("table"), start=1):
        dict_rows = table_to_dicts(table)
        if not dict_rows:
            continue
        if not {"Código", "Descripción"}.issubset(dict_rows[0]):
            continue
        title = infer_table_title(table, f"Tabla {index}")
        for row in dict_rows:
            rows.append(
                RightsTaxesRow(
                    agreement_name=title,
                    code=row.get("Código", ""),
                    description=row.get("Descripción", ""),
                    additional_code=row.get("Código adicional", ""),
                    value=row.get("Valor", ""),
                    quota_code=row.get("Código de cuota", ""),
                )
            )
    status = "ok" if rows else "empty"
    return ExtractionResult(rows=rows, status=status)
