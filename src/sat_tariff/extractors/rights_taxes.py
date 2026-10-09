"""Rights and taxes extractor."""

from __future__ import annotations

import re
import unicodedata

from .common import ExtractionResult, ascii_upper, iter_standard_section_tables, normalize_text, parse_html
from ..models import RightsTaxesRow


SAT_AGREEMENT_COLUMNS = {
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


_AGREEMENT_COLUMNS_BY_KEY = {
    _agreement_lookup_key(agreement_name): column_name
    for agreement_name, column_name in SAT_AGREEMENT_COLUMNS.items()
}
_GENERAL_AGREEMENT_KEY = _agreement_lookup_key("TRATAMIENTO GENERAL")


def agreement_column_name(agreement_name: str, duty_code: str = "DAI") -> str:
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

    fallback = re.sub(r"[^A-Z0-9]+", "_", ascii_upper(normalized_name)).strip("_") or "OTRO"
    return f"{code_label}_{fallback}"


def agreement_suffix(agreement_name: str) -> str:
    return agreement_column_name(agreement_name).removeprefix("DAI_")


def parse_rights_taxes(html: str) -> ExtractionResult[RightsTaxesRow]:
    soup = parse_html(html)
    rows: list[RightsTaxesRow] = []
    for title, dict_rows in iter_standard_section_tables(soup, max_title_length=500):
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
