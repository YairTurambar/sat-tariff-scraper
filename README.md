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

## Running the scraper

The previous positional invocation still works:

```bash
python main.py hs_codes.txt sat_tariff_data.xlsx
```

The scraper now accepts any number of numeric HS codes from the input file. It processes
every valid numeric line in order, including files with 0, 1, 19, 20, or more than 20 codes.
Non-numeric lines are skipped with a warning in `scraper.log`.

### Resume support

Each run writes a JSON state file next to the output workbook by default:

```text
sat_tariff_data.xlsx.state.json
```

Use `--resume` to continue a long run later:

```bash
python main.py hs_codes.txt sat_tariff_data.xlsx --resume
```

Resume behavior:

- skips only HS codes whose prior overall status was `Success`
- retries previously failed or incomplete HS codes
- preserves the input file order in the regenerated workbook
- rewrites the same four-sheet workbook without duplicating HS-code rows

### Delay and retry options

You can tune long-run pacing from the CLI:

```bash
python main.py hs_codes.txt sat_tariff_data.xlsx \
  --delay-between-codes 3 \
  --max-retries 2 \
  --retry-backoff 5
```

- `--delay-between-codes`: pause between HS codes; default is `2`
- `--max-retries`: bounded retries for transient per-code failures; default is `0`
- `--retry-backoff`: exponential backoff base in seconds between retries; default is `2`

CAPTCHA failures are not retried automatically in a loop. They remain session-blocking and
must still be resolved manually in the browser.
