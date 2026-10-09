# Extraction rules

## Derechos e impuestos

- Parse `TRATAMIENTO GENERAL` and every agreement/treaty rates table.
- The agreement name is resolved **structurally**, never from the position of
  the table in the document. A table number such as `Tabla 14` describes a
  position, not a trade agreement, and is never a valid identity.
- `resolve_rights_table_agreement_name()` tries, in order:
  1. the table `<caption>`;
  2. accessible attributes on the table or its containers
     (`data-agreement`, `data-title`, `aria-label`, `summary`, `title`);
  3. the nearest preceding heading, label, legend, JSF panel title or title
     row/cell of the container block, with no node limit, so long official
     names are preserved.
- The backward scan stops at the previous standard rates table, so a nested or
  sibling table can never borrow the title of another agreement's block.
- Candidates that are standard column headers, section labels or positional
  labels (`Tabla N`) are rejected by `is_valid_agreement_identity()`.
- When an identity cannot be resolved, the rows of that table are **not**
  stored. `parse_rights_taxes()` returns `status="incomplete"` with a message
  containing the evidence (duty codes and an HTML snippet) so the section can
  be re-extracted.
- Preserve table order and empty strings when cells are blank.
- Store the resolved agreement name plus the standard SAT columns.
- `SAT_AGREEMENT_COLUMN_MAP` (in `extractors/rights_taxes.py`) is the single
  source of truth that maps official names to export columns; `TRATAMIENTO
  GENERAL` yields `DAI_GENERAL`/`IVA_GENERAL` and Mexico always yields
  `DAI_MX`.

## Nomenclatura

- Parse scalar fields: `Sección`, `Capítulo:`, `Fecha inicio de vigencia:`, `Fecha fin de vigencia:`.
- Capture raw date text and a best-effort normalized ISO date.
- Parse `Código de Mercancías` and `Unidades de medida` when tables exist.
- Preserve `Códigos adicionales` text when present.
- Distinguish `ok`, `empty`, and `absent` outcomes.

## Restricciones

- Parse the `TRATAMIENTO GENERAL` restriction table when present.
- If no structured rows exist, store literal `sin información`.

## Cuotas

- Preserve quota text in `TRATAMIENTO GENERAL`.
- If no quota data exists, store exact message:
  `No se han encontrado cuotas/contingentes para el inciso consultado`
- Distinguish `no_quotas`, `load_error`, `session_expired`, and `extraction_error` statuses.
