"""Quotas extractor."""

from __future__ import annotations

from .common import ExtractionResult, ascii_upper, find_table_after_label, normalize_label, normalize_text, parse_html, table_to_labeled_dicts
from ..exporters.layouts import QUOTA_EMPTY_MESSAGE, QUOTA_FIELD_HEADERS
from ..models import QuotaRecord

NO_QUOTA_MESSAGE = QUOTA_EMPTY_MESSAGE



def parse_quotas(html: str) -> ExtractionResult[QuotaRecord]:
    soup = parse_html(html)
    page_text = normalize_text(soup.get_text(" ", strip=True))
    lower_text = page_text.casefold()
    if "sesión" in lower_text and "expir" in lower_text:
        return ExtractionResult(rows=[QuotaRecord(treatment_name="TRATAMIENTO GENERAL", message=page_text, source_status="session_expired")], status="session_expired")
    if "error" in lower_text and not soup.find_all("table"):
        return ExtractionResult(rows=[QuotaRecord(treatment_name="TRATAMIENTO GENERAL", message=page_text, source_status="load_error")], status="load_error")
    if NO_QUOTA_MESSAGE.casefold() in lower_text:
        return ExtractionResult(rows=[QuotaRecord(treatment_name="TRATAMIENTO GENERAL", message=NO_QUOTA_MESSAGE, source_status="no_quotas")], status="no_quotas")

    goods_table = find_table_after_label(soup, "Código de Mercancías", ("Cuotas", "TRATAMIENTO GENERAL"))
    goods = table_to_labeled_dicts(goods_table, ("Código", "Descripción")) if goods_table is not None else []
    treatment = "\n".join(dict.fromkeys(
        " | ".join(value for value in (row.get("CODIGO", ""), row.get("DESCRIPCION", "")) if value)
        for row in goods
    ))
    structured: list[QuotaRecord] = []
    for table in soup.find_all("table"):
        for row in table_to_labeled_dicts(table, ("Cuota", "País")):
            fields = {
                field: row.get(ascii_upper(normalize_label(header)), "")
                for field, header in QUOTA_FIELD_HEADERS.items()
            }
            structured.append(QuotaRecord(
                treatment_name="TRATAMIENTO GENERAL", message="", source_status="ok",
                general_treatment=treatment, **fields,
            ))
    if structured:
        return ExtractionResult(rows=structured, status="ok")

    tables = soup.find_all("table")
    if tables:
        messages: list[QuotaRecord] = []
        for table in tables:
            if table.find("table") is not None or table is goods_table:
                continue
            if not table_to_labeled_dicts(table, ("Descripción", "Valor")):
                continue
            text = normalize_text(table.get_text(" | ", strip=True))
            if text:
                messages.append(QuotaRecord(treatment_name="TRATAMIENTO GENERAL", message=text, source_status="ok"))
        if messages:
            return ExtractionResult(rows=messages, status="ok")

    meaningful_text = next((normalize_text(element.get_text(" ", strip=True)) for element in soup.find_all(["div", "span", "p", "li"]) if normalize_text(element.get_text(" ", strip=True))), "")
    if meaningful_text:
        return ExtractionResult(rows=[QuotaRecord(treatment_name="TRATAMIENTO GENERAL", message=meaningful_text, source_status="extraction_error")], status="extraction_error")
    return ExtractionResult(rows=[], status="extraction_error", message="Quota section not recognized")
