"""Rights and taxes extractor."""

from __future__ import annotations

import re

from .common import ExtractionResult, ascii_upper, iter_standard_section_tables, normalize_text, parse_html
from ..models import RightsTaxesRow


def agreement_suffix(agreement_name: str) -> str:
    normalized_name = ascii_upper(agreement_name).strip()
    if normalized_name == "TRATAMIENTO GENERAL":
        return "GENERAL"
    match = re.search(r"[-\u2013\u2014]\s*([A-Za-z]{2,6})\s*$", agreement_name)
    if match:
        return re.sub(r"[^A-Z0-9]+", "", ascii_upper(match.group(1))) or "OTRO"
    return re.sub(r"[^A-Z0-9]+", "_", normalized_name).strip("_") or "OTRO"


def parse_rights_taxes(html: str) -> ExtractionResult[RightsTaxesRow]:
    soup = parse_html(html)
    rows: list[RightsTaxesRow] = []
    for title, dict_rows in iter_standard_section_tables(soup):
        for row in dict_rows:
            rows.append(
                RightsTaxesRow(
                    agreement_name=normalize_text(title),
                    code=row.get("Código", ""),
                    description=row.get("Descripción", ""),
                    additional_code=row.get("Código adicional", ""),
                    value=row.get("Valor", ""),
                    quota_code=row.get("Código de cuota", ""),
                )
            )
    status = "ok" if rows else "empty"
    return ExtractionResult(rows=rows, status=status)
