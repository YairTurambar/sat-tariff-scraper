# sat-tariff-scraper

Automated scraper for Guatemalan SAT tariff (arancel integrado) data extraction to Excel.

## Output workbook

The generated Excel file keeps SAT data in four separate worksheets:

- `Derechos e impuestos`
- `Nomenclatura`
- `Restricciones`
- `Cuotas`

Each worksheet uses a **strict column whitelist**: only the columns listed below are written, and
helper/metadata fields such as `Table_Name`, `Record_Type`, `Message`, or `Resultado` are never
exported, even though they are still used internally while parsing.

- `Derechos e impuestos`: `HS_Code`, `Status`, `Overall_Status`, `Código`, the agreement duty columns
  (`DAI_GENERAL`, `IVA_GENERAL`, `DAI_MX`, `DAI_CL`, …) grouped under a merged agreement header, then
  `Código adicional` and `Código de cuota`
- `Nomenclatura`: `HS_Code`, `Status`, `Overall_Status`, `Sección`, `Capítulo:`,
  `Fecha inicio de vigencia:`, `Fecha fin de vigencia:`, `Códigos adicionales`, and the grouped
  `Unidades de medida` header with child columns `Código` and `Descripción`
- `Restricciones`: `HS_Code`, `Status`, `Overall_Status`, `Código`, `Descripción`, `Código adicional`,
  `Valor`, `Código de cuota`
- `Cuotas`: `HS_Code`, `Status`, `Overall_Status`, and a single merged `TRATAMIENTO GENERAL` column

If a section has no data or cannot be extracted for a code, the worksheet is still created and the row
is written with `HS_Code`, `Status`, and `Overall_Status` while the remaining required columns stay empty.

### Normalized section output

- `Derechos e impuestos` pivots every duty/agreement table into its own column; `Código` keeps the
  source codes (for example `DAI | IVA`) that feed the pivot, and rows are keyed by
  `Código adicional`/`Código de cuota`
- `Derechos e impuestos` maps each agreement table to a `DAI_<SUFFIX>`/`IVA_<SUFFIX>`-style column using
  a data-driven suffix: the general schedule becomes `GENERAL`, an explicit trailing code on the
  agreement name (for example "... – MX") is used verbatim, and agreements without an explicit code fall
  back to a sanitized slug of their name. The agreement name itself is never exported as a column.
- `Restricciones` is exported as one row per source restriction row, preserving duplicates
- `Cuotas` writes only the SAT portal informational text to the merged `TRATAMIENTO GENERAL` column (for
  example `No se han encontrado cuotas/contingentes para el inciso consultado`). The displayed text is
  preserved exactly; the `Resultados de la búsqueda: ` prefix is never invented or duplicated.
- `Nomenclatura` is exported as one row per `Unidades de medida` record (or a single row when none
  exists), repeating the scalar fields and the `Códigos adicionales` message, typically
  `No se han encontrado códigos adicionales asociados al inciso consultado`

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
