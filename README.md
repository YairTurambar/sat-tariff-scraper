# sat-tariff-scraper

Automated scraper for Guatemalan SAT tariff (arancel integrado) data extraction to Excel.

## Output workbook

The generated Excel file keeps SAT data in four separate worksheets:

- `Derechos e impuestos`
- `Nomenclatura`
- `Restricciones`
- `Cuotas`

Each worksheet contains:

- `HS_Code`
- `Status`
- `Overall_Status`
- normalized, section-specific extracted fields for that SAT section

If a section has no data or cannot be extracted for a code, the worksheet is still created and the row is written with `HS_Code` and `Status`.

### Normalized section output

- `Derechos e impuestos`, `Restricciones`, and `Cuotas` are exported as one row per source treatment/agreement table row, preserving:
  - `Table_Name`
  - `Código`
  - `Descripción`
  - `Código adicional`
  - `Valor`
  - `Código de cuota`
- `Nomenclatura` is exported as one row per named table/content block, preserving the scalar fields:
  - `Sección`
  - `Capítulo:`
  - `Fecha inicio de vigencia:`
  - `Fecha fin de vigencia:`
  - plus all columns from `Código de Mercancías`, the complete `Códigos adicionales` content or empty-state message, `Unidades de medida`, and the content/status of `Clasificadores estadísticos`, `Descripciones mínimas`, and `Criterios de Clasificación`

## CAPTCHA handling

CAPTCHA solving remains manual. When SAT shows a CAPTCHA, solve it in the browser window and the scraper will continue after the CAPTCHA field disappears.
