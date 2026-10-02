# Extraction rules

## Derechos e impuestos

- Parse `TRATAMIENTO GENERAL` and any following agreement/treaty tables.
- Preserve table order and titles.
- Preserve empty strings when cells are blank.
- Store agreement name plus standard SAT columns.

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
