"""Common HTML extraction utilities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Generic, TypeVar

from bs4 import BeautifulSoup, NavigableString, Tag

T = TypeVar("T")
STANDARD_HEADERS = ("Código", "Descripción", "Código adicional", "Valor", "Código de cuota")


@dataclass(slots=True)
class ExtractionResult(Generic[T]):
    rows: list[T]
    status: str
    message: str | None = None



def parse_html(html: str) -> BeautifulSoup:
    return BeautifulSoup(html or "", "html.parser")



def normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()



def normalize_label(value: str | None) -> str:
    return normalize_text(value).rstrip(":").casefold()



def direct_rows(table: Tag) -> list[Tag]:
    return [row for row in table.find_all("tr") if row.find_parent("table") is table]



def direct_cells(row: Tag) -> list[Tag]:
    return [cell for cell in row.find_all(["td", "th"]) if cell.find_parent("tr") is row]



def cell_text(cell: Tag) -> str:
    return normalize_text(cell.get_text(" ", strip=True))



def table_to_dicts(table: Tag) -> list[dict[str, str]]:
    rows = direct_rows(table)
    if not rows:
        return []
    headers = [cell_text(cell) or f"Column_{index}" for index, cell in enumerate(direct_cells(rows[0]), start=1)]
    extracted: list[dict[str, str]] = []
    for row in rows[1:]:
        values = [cell_text(cell) for cell in direct_cells(row)]
        if not any(values):
            continue
        extracted.append({header: values[index] if index < len(values) else "" for index, header in enumerate(headers)})
    return extracted



def find_anchor(soup: BeautifulSoup, label: str) -> Tag | None:
    target = normalize_label(label)
    for element in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "strong", "b", "label", "legend", "span", "div", "p", "td", "th"]):
        if normalize_label(element.get_text(" ", strip=True)) == target:
            return element
    return None



def infer_table_title(table: Tag, fallback: str = "") -> str:
    caption = table.find("caption")
    if caption:
        text = cell_text(caption)
        if text:
            return text
    ignored = {normalize_label(header) for header in STANDARD_HEADERS}
    for element in table.find_all_previous(["h1", "h2", "h3", "h4", "h5", "h6", "strong", "b", "label", "legend", "div", "span", "p"], limit=20):
        if element.find_parent("table") is not None:
            continue
        text = normalize_text(element.get_text(" ", strip=True))
        if not text or len(text) > 120 or normalize_label(text) in ignored:
            continue
        return text
    return fallback



def find_table_after_label(soup: BeautifulSoup, label: str, stop_labels: tuple[str, ...] = ()) -> Tag | None:
    anchor = find_anchor(soup, label)
    stop_set = {normalize_label(item) for item in stop_labels if item != label}
    if anchor is not None:
        for element in anchor.find_all_next():
            if not isinstance(element, Tag):
                continue
            text = normalize_text(element.get_text(" ", strip=True))
            if text and normalize_label(text) in stop_set:
                break
            if element.name == "table":
                return element
    for index, table in enumerate(soup.find_all("table"), start=1):
        title = infer_table_title(table, f"Tabla {index}")
        if normalize_label(title) == normalize_label(label):
            return table
    return None



def extract_labeled_value(soup: BeautifulSoup, label: str) -> str:
    target = normalize_label(label)
    for row in soup.find_all("tr"):
        cells = direct_cells(row)
        if len(cells) >= 2 and normalize_label(cell_text(cells[0])) == target:
            return cell_text(cells[1])
    pattern = re.compile(rf"^{re.escape(normalize_text(label).rstrip(':'))}\s*:?\s*(.+)$", re.IGNORECASE)
    for element in soup.find_all(["div", "span", "p", "li", "td", "th", "strong", "b"]):
        text = normalize_text(element.get_text(" ", strip=True))
        if not text:
            continue
        match = pattern.match(text)
        if match:
            return match.group(1).strip()
        if normalize_label(text) != target:
            continue
        for sibling in element.next_siblings:
            if isinstance(sibling, NavigableString):
                value = normalize_text(str(sibling))
            else:
                value = normalize_text(sibling.get_text(" ", strip=True))
            if value:
                return value
    return ""



def extract_text_after_label(soup: BeautifulSoup, label: str, stop_labels: tuple[str, ...]) -> str:
    anchor = find_anchor(soup, label)
    if anchor is None:
        return ""
    stop_set = {normalize_label(item) for item in stop_labels if item != label}
    for element in anchor.find_all_next():
        if isinstance(element, Tag):
            text = normalize_text(element.get_text(" ", strip=True))
            if text and normalize_label(text) in stop_set:
                break
            if element.name == "table" or element.find_parent("table") is not None:
                continue
            if text and normalize_label(text) != normalize_label(label):
                return text
        elif isinstance(element, NavigableString):
            text = normalize_text(str(element))
            if text:
                return text
    return ""



def parse_date_attempt(value: str) -> str | None:
    cleaned = normalize_text(value)
    if not cleaned:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue
    return None
