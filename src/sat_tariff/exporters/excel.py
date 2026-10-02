"""Excel export implementation."""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil
from typing import Any
import unicodedata

from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter

from ..config import AppConfig
from ..extractors.rights_taxes import agreement_suffix as _agreement_suffix
from ..validation.output_validator import validate_workbook_structure
from .layouts import DUTY_GROUP_ORDER_HINT, FORBIDDEN_EXPORT_COLUMNS, NOMENCLATURE_HEADERS, QUOTAS_HEADERS, RESTRICTIONS_HEADERS, RIGHTS_BASE_HEADERS, RIGHTS_TRAILING_HEADERS, SHEET_ORDER, TEXT_COLUMNS
from .styles import autosize_columns, set_data_row_heights, style_data_cells, style_headers


def _ascii_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").upper()
    slug = re.sub(r"[^A-Z0-9]+", "_", ascii_value).strip("_")
    return slug or "OTRO"



def _base_row(bundle: dict[str, Any], section_key: str) -> dict[str, Any]:
    return {
        "HS_Code": bundle["raw_code"],
        "Status": bundle.get(section_key, {}).get("status") or bundle["state"],
        "Overall_Status": bundle["state"],
    }



def _rights_column_metadata(bundles: list[dict[str, Any]]) -> "OrderedDict[str, tuple[str, str, str]]":
    """Map each dynamic rights column name to (code_label, suffix, group_label).

    ``group_label`` is the first full agreement name seen for that suffix
    (e.g. ``"TRATAMIENTO GENERAL"`` or ``"Tratado de Libre Comercio - MX"``),
    used as the merged group header above the per-code value columns.
    """
    metadata: "OrderedDict[str, tuple[str, str, str]]" = OrderedDict()
    for bundle in bundles:
        for row in bundle.get("rights", {}).get("rows", []):
            code_label = _ascii_slug(row.get("code", ""))
            agreement_name = row.get("agreement_name", "")
            suffix = _agreement_suffix(agreement_name)
            column_name = f"{code_label}_{suffix}"
            if column_name == "_":
                continue
            metadata.setdefault(column_name, (code_label, suffix, agreement_name.strip() or suffix))
    return metadata



def _rights_dynamic_columns(metadata: "OrderedDict[str, tuple[str, str, str]]") -> list[str]:
    ordered_names = list(metadata.keys())
    original_index = {name: index for index, name in enumerate(ordered_names)}
    hint_order = {suffix: index for index, suffix in enumerate(DUTY_GROUP_ORDER_HINT)}

    def sort_key(column_name: str) -> tuple[int, int, str]:
        _code, suffix, _label = metadata[column_name]
        if suffix == "GENERAL":
            return (0, original_index[column_name], column_name)
        hint_index = hint_order.get(suffix, len(DUTY_GROUP_ORDER_HINT))
        return (1 + hint_index, original_index[column_name], column_name)

    return sorted(ordered_names, key=sort_key)



def _build_rights_rows(bundles: list[dict[str, Any]], dynamic_columns: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bundle in bundles:
        base = _base_row(bundle, "rights")
        section_rows = bundle.get("rights", {}).get("rows", [])
        if not section_rows:
            rows.append({**base, "Código": "", **{column: "" for column in dynamic_columns}, "Código adicional": "", "Código de cuota": ""})
            continue
        grouped: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()
        for source in section_rows:
            key = (source.get("additional_code", ""), source.get("quota_code", ""))
            target = grouped.setdefault(key, {**base, "Código": "", **{column: "" for column in dynamic_columns}, "Código adicional": key[0], "Código de cuota": key[1]})
            column_name = f"{_ascii_slug(source.get('code', ''))}_{_agreement_suffix(source.get('agreement_name', ''))}"
            existing = target.get(column_name, "")
            new_value = source.get("value", "")
            if new_value:
                target[column_name] = f"{existing}\n{new_value}".strip()
            source_code = source.get("code", "")
            if source_code:
                merged_codes = list(
                    OrderedDict.fromkeys(
                        filter(
                            None,
                            (target["Código"] + " | " + source_code).strip(" | ").split(" | "),
                        )
                    )
                )
                target["Código"] = " | ".join(merged_codes)
        rows.extend(grouped.values())
    return rows



def _build_nomenclature_rows(bundles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bundle in bundles:
        base = _base_row(bundle, "nomenclature")
        section_rows = bundle.get("nomenclature", {}).get("rows", [])
        scalars = {"Sección": "", "Capítulo:": "", "Fecha inicio de vigencia:": "", "Fecha fin de vigencia:": "", "Códigos adicionales": ""}
        units: list[tuple[str, str]] = []
        for record in section_rows:
            scalars["Sección"] = scalars["Sección"] or record.get("section", "")
            scalars["Capítulo:"] = scalars["Capítulo:"] or record.get("chapter", "")
            scalars["Fecha inicio de vigencia:"] = scalars["Fecha inicio de vigencia:"] or record.get("effective_from_raw", "")
            scalars["Fecha fin de vigencia:"] = scalars["Fecha fin de vigencia:"] or record.get("effective_to_raw", "")
            scalars["Códigos adicionales"] = scalars["Códigos adicionales"] or record.get("additional_codes_text", "")
            if record.get("record_type") == "unit":
                units.append((record.get("unit_code", ""), record.get("unit_description", "")))
        shared = {**base, **scalars}
        if not units:
            rows.append({**shared, "Código": "", "Descripción": ""})
        else:
            for code, description in units:
                rows.append({**shared, "Código": code, "Descripción": description})
    return rows


def _assert_no_forbidden_headers(headers: list[str]) -> None:
    leaked = FORBIDDEN_EXPORT_COLUMNS.intersection(headers)
    if leaked:
        raise ValueError(f"Forbidden export columns leaked into workbook: {sorted(leaked)}")



def _build_restrictions_rows(bundles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bundle in bundles:
        base = _base_row(bundle, "restrictions")
        section_rows = bundle.get("restrictions", {}).get("rows", [])
        if not section_rows:
            rows.append({**base, "Código": "", "Descripción": "", "Código adicional": "", "Valor": "", "Código de cuota": ""})
            continue
        for record in section_rows:
            rows.append({
                **base,
                "Código": record.get("code", ""),
                "Descripción": record.get("description", ""),
                "Código adicional": record.get("additional_code", ""),
                "Valor": record.get("value", ""),
                "Código de cuota": record.get("quota_code", ""),
            })
    return rows



def _build_quotas_rows(bundles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bundle in bundles:
        base = _base_row(bundle, "quotas")
        messages = [record.get("message", "") for record in bundle.get("quotas", {}).get("rows", []) if record.get("message")]
        rows.append({**base, "TRATAMIENTO GENERAL": "\n".join(messages)})
    return rows



def _write_headers(ws, headers: list[str]) -> None:
    ws.append(headers)



def _write_rights_sheet(
    ws,
    rows: list[dict[str, Any]],
    dynamic_columns: list[str],
    column_metadata: "OrderedDict[str, tuple[str, str, str]]",
) -> list[str]:
    """Write the flat rights header used by the reference worksheet."""
    all_headers = RIGHTS_BASE_HEADERS + dynamic_columns + RIGHTS_TRAILING_HEADERS
    ws.append(all_headers)
    for row in rows:
        ws.append([row.get(header, "") for header in all_headers])

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(max(1, len(all_headers)))}{max(ws.max_row, 1)}"
    return all_headers



def _write_nomenclature_sheet(ws, rows: list[dict[str, Any]]) -> None:
    ws.append(NOMENCLATURE_HEADERS[:-2] + ["Unidades de medida", None])
    ws.append(NOMENCLATURE_HEADERS[:-2] + ["Código", "Descripción"])
    ws.merge_cells(start_row=1, start_column=1, end_row=2, end_column=1)
    ws.merge_cells(start_row=1, start_column=2, end_row=2, end_column=2)
    ws.merge_cells(start_row=1, start_column=3, end_row=2, end_column=3)
    ws.merge_cells(start_row=1, start_column=4, end_row=2, end_column=4)
    ws.merge_cells(start_row=1, start_column=5, end_row=2, end_column=5)
    ws.merge_cells(start_row=1, start_column=6, end_row=2, end_column=6)
    ws.merge_cells(start_row=1, start_column=7, end_row=2, end_column=7)
    ws.merge_cells(start_row=1, start_column=8, end_row=2, end_column=8)
    ws.merge_cells(start_row=1, start_column=9, end_row=1, end_column=10)
    for row in rows:
        ws.append([row.get(header, "") for header in NOMENCLATURE_HEADERS])
    ws.freeze_panes = "A3"
    ws.auto_filter.ref = f"A2:J{max(ws.max_row, 2)}"
    style_headers(ws, 2)
    style_data_cells(ws, 3)



def _apply_text_formats(ws, header_rows: int) -> None:
    header_values = {}
    for row_index in range(1, min(ws.max_row, header_rows) + 1):
        for col_index in range(1, ws.max_column + 1):
            value = ws.cell(row=row_index, column=col_index).value
            if value:
                header_values[col_index] = value
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row):
        for cell in row:
            header = header_values.get(cell.column)
            if header in TEXT_COLUMNS:
                cell.number_format = "@"



def _backup_existing(destination: Path) -> None:
    backup_dir = destination.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    shutil.copy2(destination, backup_dir / f"{destination.stem}-{timestamp}{destination.suffix}")



def export_workbook(bundles: list[dict[str, Any]], config: AppConfig, output_path: str | Path | None = None) -> Path:
    destination = Path(output_path or config.output_xlsx)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and config.backup_output:
        _backup_existing(destination)

    workbook = Workbook()
    default_sheet = workbook.active
    workbook.remove(default_sheet)

    dynamic_rights_metadata = _rights_column_metadata(bundles)
    dynamic_rights = _rights_dynamic_columns(dynamic_rights_metadata)
    rights_headers = RIGHTS_BASE_HEADERS + dynamic_rights + RIGHTS_TRAILING_HEADERS
    sections = {
        "Derechos e impuestos": _build_rights_rows(bundles, dynamic_rights),
        "Nomenclatura": _build_nomenclature_rows(bundles),
        "Restricciones": _build_restrictions_rows(bundles),
        "Cuotas": _build_quotas_rows(bundles),
    }

    for sheet_name in SHEET_ORDER:
        ws = workbook.create_sheet(sheet_name)
        if sheet_name == "Derechos e impuestos":
            _assert_no_forbidden_headers(rights_headers)
            _write_rights_sheet(ws, sections[sheet_name], dynamic_rights, dynamic_rights_metadata)
            style_headers(ws, 1)
            style_data_cells(ws, 2)
            header_rows = 1
        elif sheet_name == "Nomenclatura":
            _assert_no_forbidden_headers(NOMENCLATURE_HEADERS)
            _write_nomenclature_sheet(ws, sections[sheet_name])
            header_rows = 2
        elif sheet_name == "Restricciones":
            _assert_no_forbidden_headers(RESTRICTIONS_HEADERS)
            _write_headers(ws, RESTRICTIONS_HEADERS)
            for row in sections[sheet_name]:
                ws.append([row.get(header, "") for header in RESTRICTIONS_HEADERS])
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = f"A1:H{max(ws.max_row, 1)}"
            style_headers(ws, 1)
            style_data_cells(ws, 2)
            header_rows = 1
        else:
            _assert_no_forbidden_headers(QUOTAS_HEADERS)
            _write_headers(ws, QUOTAS_HEADERS)
            for row in sections[sheet_name]:
                ws.append([row.get(header, "") for header in QUOTAS_HEADERS])
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = f"A1:D{max(ws.max_row, 1)}"
            style_headers(ws, 1)
            style_data_cells(ws, 2)
            header_rows = 1
        autosize_columns(ws)
        set_data_row_heights(ws, header_rows + 1)
        _apply_text_formats(ws, header_rows)

    temp_path = destination.with_name(f"{destination.stem}.tmp{destination.suffix}")
    workbook.save(temp_path)
    load_workbook(temp_path)
    validate_workbook_structure(temp_path)
    os.replace(temp_path, destination)
    return destination
