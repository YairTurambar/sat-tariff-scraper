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
- grouped blue headers in the generated workbook where SAT presents grouped data, including:
  - `Derechos e impuestos`: agreement/treatment duty columns such as `DAI_GENERAL`, `IVA_GENERAL`, `DAI_MX`, `DAI_CL`, etc., followed by `Código adicional` and `Código de cuota`
  - `Nomenclatura`: leading scalar columns plus the grouped `Unidades de medida` header with child columns `Código` and `Descripción`
  - `Restricciones`: ordered columns `Código`, `Descripción`, `Código adicional`, `Valor`, `Código de cuota`
  - `Cuotas`: a dedicated `Resultado` column containing the SAT message/result text

If a section has no data or cannot be extracted for a code, the worksheet is still created and the row is written with `HS_Code`, `Status`, and `Overall_Status`.

### Normalized section output

- `Derechos e impuestos` is exported with agreement-specific duty columns per HS row so that each treatment remains in its own column instead of a generic row blob
- `Restricciones` is exported as one row per source restriction row, preserving duplicates and keeping `Código`, `Descripción`, `Código adicional`, `Valor`, and `Código de cuota` in that order
- `Cuotas` writes the SAT portal result text to `Resultado`, including the empty-state wording when no quota exists, while preserving raw extracted fields after the required columns
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
