"""Quotas extractor."""

from __future__ import annotations

from bs4 import Tag

from .common import ExtractionResult, ascii_upper, cell_text, direct_cells, direct_rows, find_table_after_label, normalize_label, normalize_text, parse_html, table_to_labeled_dicts
from ..exporters.layouts import QUOTA_EMPTY_MESSAGE, QUOTA_FIELD_HEADERS
from ..models import QuotaRecord

NO_QUOTA_MESSAGE = QUOTA_EMPTY_MESSAGE
EXTENSIONS_TITLE = "Ampliaciones de la cuota en la vigencia definida"
REQUIRED_QUOTA_HEADERS = tuple(
    header for field, header in QUOTA_FIELD_HEADERS.items() if field != "extensions"
)


def _quota_cell_text(cell: Tag) -> str:
    popup = cell.find("div", class_="tituloPopPup")
    if popup is not None and any(
        normalize_label(label.get_text(" ", strip=True)) == normalize_label(EXTENSIONS_TITLE)
        for label in popup.find_all("label")
    ):
        table = popup.find("table")
        if table is not None:
            return "\n".join(
                " | ".join(cell_text(item) for item in direct_cells(row))
                for row in direct_rows(table)
                if any(cell_text(item) for item in direct_cells(row))
            )
    if cell.find("table") is not None:
        raise ValueError("Unrecognized nested quota table")
    return cell_text(cell)



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
    if not goods:
        for table in soup.select('table[id$=":incisosTable"]'):
            for row in table.select("tr.filaInciso"):
                code = row.select_one('span[id$=":inciso"].columnaCodigoSubpartida')
                description = row.select_one("span.columnaNombreSubpartida")
                if code is not None and description is not None and cell_text(code):
                    goods.append({"CODIGO": cell_text(code), "DESCRIPCION": cell_text(description)})
    treatment = "\n".join(dict.fromkeys(
        " | ".join(value for value in (row.get("CODIGO", ""), row.get("DESCRIPCION", "")) if value)
        for row in goods
    ))
    structured: list[QuotaRecord] = []
    identifying_headers = {
        ascii_upper(normalize_label(header)) for header in REQUIRED_QUOTA_HEADERS
        if header != "País"
    }
    for table in soup.find_all("table"):
        if not any(
            ascii_upper(normalize_label(cell_text(cell))) in identifying_headers
            for row in direct_rows(table) for cell in direct_cells(row)
        ):
            continue
        try:
            quota_rows = table_to_labeled_dicts(
                table, REQUIRED_QUOTA_HEADERS, strict_width=True, data_cell_text=_quota_cell_text,
            )
        except ValueError as exc:
            return ExtractionResult(rows=[], status="extraction_error", message=str(exc))
        if not quota_rows:
            return ExtractionResult(rows=[], status="extraction_error", message="Quota headers not recognized")
        for row in quota_rows:
            fields = {
                field: row.get(ascii_upper(normalize_label(header)), "")
                for field, header in QUOTA_FIELD_HEADERS.items()
            }
            if not fields["extensions"] and row.get("", "").startswith(EXTENSIONS_TITLE):
                fields["extensions"] = row[""]
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
