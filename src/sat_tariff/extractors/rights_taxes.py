"""Rights and taxes extractor."""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Final

from bs4 import BeautifulSoup, Tag

from .common import (
    ExtractionResult,
    STANDARD_HEADERS,
    ascii_upper,
    cell_text,
    is_standard_section_table,
    normalize_label,
    normalize_text,
    parse_html,
    table_to_dicts,
)
from ..models import RightsTaxesRow

LOGGER = logging.getLogger(__name__)


SAT_AGREEMENT_COLUMN_MAP: Final = {
    "Acuerdo de Alcance Parcial entre el Gobierno de la República de Guatemala y el Gobierno de Belice - BZ": "DAI_BZ",
    "Tratado de Libre Comercio Entre Centroamérica y Chile - CL": "DAI_CL",
    "Tratado de Libre Comercio entre la República de Colombia y las Repúblicas de El Salvador, Guatemala y Honduras - CO": "DAI_CO",
    "Tratado de Libre Comercio - República Dominicana - Centroamérica - Estados Unidos de América - US": "DAI_US",
    "Acuerdo de Alcance Parcial entre la República de Guatemala y la República de Cuba - CU": "DAI_CU",
    "Tratado de Libre Comercio entre Centroamérica y República Dominicana - DO": "DAI_DO",
    "Acuerdo de Alcance Parcial de Complementación entre el Gobierno de la República de Guatemala y el Gobierno de la República del Ecuador - EC": "DAI_EC",
    "Acuerdo por el que se establece una Asociación entre la Unión Europea y sus Estados Miembros, por un lado, y Centroamérica, por otro (UE) - ADAE": "DAI_AE",
    "Tratado de Libre Comercio Entre Los Estados Unidos Mexicanos y las Repúblicas de Costa Rica, El Salvador, Guatemala, Honduras y Nicaragua - MX": "DAI_MX",
    "Tratado de Libre Comercio y de Intercambio Preferencial entre las Repúblicas de Panamá y Guatemala - PA": "DAI_PA",
    "Tratado de Libre Comercio entre la República de Guatemala y la República de China (Taiwán) - TW": "DAI_TW",
    "Acuerdo por el que se Establece una Asociación Entre Reino Unido de Gran Bretaña e Irlanda del Norte y Centroamérica - UK": "DAI_UK",
    "Tratado de Libre Comercio entre el Gobierno de la República de Guatemala y el Gobierno del Estado de Israel - IL": "DAI_IL",
}

_HYPHENS_RE = re.compile(r"\s*[-\u2010-\u2015\u2212]\s*")
_EXPLICIT_CODE_RE = re.compile(r"\s-\s([A-Za-z][A-Za-z0-9]{1,9})$")


def normalize_agreement_name(agreement_name: str) -> str:
    normalized = unicodedata.normalize("NFKC", agreement_name or "")
    normalized = _HYPHENS_RE.sub(" - ", normalized)
    return normalize_text(normalized)


def _agreement_lookup_key(agreement_name: str) -> str:
    normalized = unicodedata.normalize("NFKD", normalize_agreement_name(agreement_name))
    without_accents = "".join(character for character in normalized if not unicodedata.combining(character))
    return without_accents.casefold()


def agreement_lookup_key(agreement_name: str) -> str:
    """Return the accent- and case-insensitive identity used for matching."""
    return _agreement_lookup_key(agreement_name)


_AGREEMENT_COLUMNS_BY_KEY = {
    _agreement_lookup_key(agreement_name): column_name
    for agreement_name, column_name in SAT_AGREEMENT_COLUMN_MAP.items()
}
_GENERAL_AGREEMENT_KEY = _agreement_lookup_key("TRATAMIENTO GENERAL")


def agreement_column_name(agreement_name: str, duty_code: str = "DAI") -> str | None:
    code_label = re.sub(r"[^A-Z0-9]+", "_", ascii_upper(duty_code)).strip("_") or "DAI"
    lookup_key = _agreement_lookup_key(agreement_name)
    if lookup_key == _GENERAL_AGREEMENT_KEY:
        return f"{code_label}_GENERAL"

    mapped_column = _AGREEMENT_COLUMNS_BY_KEY.get(lookup_key)
    if mapped_column:
        mapped_suffix = mapped_column.partition("_")[2]
        return f"{code_label}_{mapped_suffix}"

    normalized_name = normalize_agreement_name(agreement_name)
    match = _EXPLICIT_CODE_RE.search(normalized_name)
    if match:
        suffix = re.sub(r"[^A-Z0-9]+", "", ascii_upper(match.group(1)))
        if suffix:
            return f"{code_label}_{suffix}"

    return None


def agreement_suffix(agreement_name: str) -> str:
    return (agreement_column_name(agreement_name) or "").removeprefix("DAI_")


MAX_AGREEMENT_NAME_LENGTH: Final = 500
GENERAL_TREATMENT_NAME: Final = "TRATAMIENTO GENERAL"

_POSITIONAL_IDENTITY_RE = re.compile(r"^(?:tabla|table)\s*(?:no\.?|num\.?|#)?\s*\d+$")
_TITLE_TAGS: Final = (
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "strong",
    "b",
    "label",
    "legend",
    "caption",
    "div",
    "span",
    "p",
    "td",
    "th",
)
_TITLE_ATTRIBUTES: Final = ("data-agreement", "data-title", "aria-label", "summary", "title")
_NON_IDENTITY_KEYS: Final = frozenset(
    _agreement_lookup_key(label)
    for label in (
        *STANDARD_HEADERS,
        "Derechos e impuestos",
        "Nomenclatura",
        "Restricciones",
        "Cuotas",
        "Resultado",
        "Consulta",
        "Buscar",
        "Regresar",
        "Imprimir",
        "Inciso",
        "Sin información",
    )
)


def is_positional_identity(agreement_name: str) -> bool:
    """Return ``True`` for placeholder identities such as ``"Tabla 14"``.

    Table numbers describe a position in the document, never a trade agreement,
    so they must never reach SQLite nor the workbook.
    """
    return bool(_POSITIONAL_IDENTITY_RE.match(_agreement_lookup_key(agreement_name)))


def is_valid_agreement_identity(agreement_name: str) -> bool:
    """Return ``True`` when ``agreement_name`` can identify a real agreement."""
    normalized = normalize_agreement_name(agreement_name)
    if not normalized or len(normalized) > MAX_AGREEMENT_NAME_LENGTH:
        return False
    if is_positional_identity(normalized):
        return False
    if _agreement_lookup_key(normalized) in _NON_IDENTITY_KEYS:
        return False
    return sum(1 for character in normalized if character.isalpha()) >= 3


def _is_standard_table(table: Tag, cache: dict[int, bool] | None = None) -> bool:
    if cache is None:
        return is_standard_section_table(table)
    key = id(table)
    if key not in cache:
        cache[key] = is_standard_section_table(table)
    return cache[key]


def _inside_standard_table(element: Tag, cache: dict[int, bool] | None = None) -> bool:
    parent_table = element.find_parent("table")
    while parent_table is not None:
        if _is_standard_table(parent_table, cache):
            return True
        parent_table = parent_table.find_parent("table")
    return False


def _contains_standard_table(element: Tag, cache: dict[int, bool] | None = None) -> bool:
    return any(_is_standard_table(nested, cache) for nested in element.find_all("table"))


def _identity_from_attributes(table: Tag, cache: dict[int, bool] | None = None) -> str | None:
    element: Tag | None = table
    while isinstance(element, Tag):
        if element is not table and _contains_standard_table_other_than(element, table, cache):
            break
        for attribute in _TITLE_ATTRIBUTES:
            value = normalize_text(element.get(attribute) if hasattr(element, "get") else "")
            if is_valid_agreement_identity(value):
                return normalize_agreement_name(value)
        element = element.parent
    return None


def _contains_standard_table_other_than(
    element: Tag, table: Tag, cache: dict[int, bool] | None = None
) -> bool:
    return any(
        nested is not table and _is_standard_table(nested, cache) for nested in element.find_all("table")
    )


def resolve_rights_table_agreement_name(
    table: Tag, cache: dict[int, bool] | None = None
) -> str | None:
    """Resolve the official agreement name that owns ``table``.

    The association is purely structural: caption, accessible attributes,
    sibling headings/labels and the title row of the JSF container that wraps
    the rates table. The index of the table in the document is never used as an
    identity. ``None`` means the identity could not be resolved with certainty.
    """
    caption = table.find("caption")
    if caption is not None and caption.find_parent("table") is table:
        text = cell_text(caption)
        if is_valid_agreement_identity(text):
            return normalize_agreement_name(text)

    attribute_identity = _identity_from_attributes(table, cache)
    if attribute_identity:
        return attribute_identity

    for element in table.find_all_previous():
        if not isinstance(element, Tag):
            continue
        if element.name == "table" and _is_standard_table(element, cache):
            # Another rates table sits between this candidate and ``table``:
            # anything before it belongs to that block, never to this one.
            break
        if element.name not in _TITLE_TAGS:
            continue
        if _inside_standard_table(element, cache) or _contains_standard_table(element, cache):
            continue
        text = normalize_text(element.get_text(" ", strip=True))
        if not is_valid_agreement_identity(text):
            continue
        return normalize_agreement_name(text)
    return None


def extract_rights_table_blocks(soup: BeautifulSoup) -> list[tuple[Tag, str | None]]:
    """Return every rates table of the section with its resolved agreement name."""
    cache: dict[int, bool] = {}
    blocks: list[tuple[Tag, str | None]] = []
    for table in soup.find_all("table"):
        if not _is_standard_table(table, cache):
            continue
        blocks.append((table, resolve_rights_table_agreement_name(table, cache)))
    return blocks


def _table_evidence(table: Tag) -> str:
    codes = [row.get("Código", "") for row in table_to_dicts(table)]
    snippet = normalize_text(str(table))[:200]
    return f"códigos={codes!r} html={snippet!r}"


def parse_rights_taxes(html: str) -> ExtractionResult[RightsTaxesRow]:
    soup = parse_html(html)
    rows: list[RightsTaxesRow] = []
    unresolved: list[str] = []
    for table, agreement_name in extract_rights_table_blocks(soup):
        if agreement_name is None:
            unresolved.append(_table_evidence(table))
            continue
        for row in table_to_dicts(table):
            rows.append(
                RightsTaxesRow(
                    agreement_name=agreement_name,
                    code=row.get("Código", ""),
                    description=row.get("Descripción", ""),
                    additional_code=row.get("Código adicional", ""),
                    value=row.get("Valor", ""),
                    quota_code=row.get("Código de cuota", ""),
                )
            )
    if unresolved:
        message = (
            "No se pudo resolver el nombre oficial del acuerdo para "
            f"{len(unresolved)} tabla(s) de 'Derechos e impuestos'. Las tasas afectadas no se "
            "guardan con una identidad posicional ('Tabla N'); hay que reextraer la sección. "
            "Evidencia: " + " | ".join(unresolved)
        )
        LOGGER.error("%s", message)
        return ExtractionResult(rows=rows, status="incomplete", message=message)
    status = "ok" if rows else "empty"
    return ExtractionResult(rows=rows, status=status)
