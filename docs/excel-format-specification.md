# Excel format specification

## Provenance and rendering limitation (read this first)

This specification is meant to be **verifiable**: every rule below maps to an
assertion either in `tests/unit/test_exporters.py` /
`src/sat_tariff/validation/output_validator.py` (structural, always run) or in
`tests/visual/test_visual_regression.py` (tolerant pixel comparison,
conditionally run — see "Visual comparison" below).

The four real reference screenshots are available under `references/`.
Their original display names are accepted as aliases for the canonical
lowercase names. Direct inspection confirmed PNG/RGBA format and these
dimensions: Derechos e impuestos 1853×91, Nomenclatura 1531×124,
Restricciones 1492×147, and Cuotas 1460×137.

This specification is derived from two verifiable, evidence-based sources:

1. The project's **pre-migration legacy implementation** (`sat_scraper.py`,
   `config.py`, removed by PR #8 when the code moved to `src/sat_tariff/`),
   which was iteratively built and adjusted across several earlier, merged
   pull requests explicitly described as matching the reference screenshots
   (closed PR #5 "Match SAT Excel export layout to reference sheets", #6, #7).
   That implementation's styling constants, grouped-header logic, and column
   whitelists are the strongest available proxy for the real screenshots.
2. The literal textual requirements in the task description (sheet names,
   order, required labels like `TRATAMIENTO GENERAL`, the `Unidades de
   medida` grouping, the exact "no quotas" message).

The visual command and test render with LibreOffice and compare against those
four files. They report mean absolute pixel difference and SSIM after
whitespace trimming/rescaling, plus source and normalized dimensions. The
comparison is deliberately tolerant because LibreOffice is not Excel's
rendering engine; it is not an exact pixel-equivalence test.

The latest offline run (200 dpi, non-destructive normalization) passed all
four sheets and reported mean absolute difference/SSIM of 0.1124/0.4912 for
Derechos e impuestos, 0.0973/0.5391 for Nomenclatura, 0.1179/0.4775 for
Restricciones and 0.1295/0.5341 for Cuotas, against the previous
0.2017/0.0762, 0.1540/0.2190, 0.1805/0.1303 and 0.2593/0.0818. The design
thresholds were therefore *raised* to mean ≤ 0.18 and SSIM ≥ 0.35. This is an
honest cross-renderer result, not a pixel-perfect equivalence claim; see
`references/README.md` for dimensions and the remaining limitations.

The second reference level, the LibreOffice baseline under
`tests/visual/baselines/libreoffice/`, *is* compared pixel by pixel (measured
mean 0.0000 / SSIM 1.0000) because both sides come from the same engine and
configuration.

## Workbook-level rules

- Exactly four sheets, in this exact order (verified in
  `test_exporter_builds_expected_workbook_structure` and
  `output_validator.validate_workbook_structure`):
  1. `Derechos e impuestos`
  2. `Nomenclatura`
  3. `Restricciones`
  4. `Cuotas`
- No other sheet exists (`"Sheet"`, openpyxl's default sheet, is explicitly
  removed).
- No internal parsing/metadata columns leak into any sheet. The forbidden
  set (`FORBIDDEN_EXPORT_COLUMNS` in `exporters/layouts.py`) is
  `{"Table_Name", "Record_Type", "Message", "Resultado", "Content",
  "Input_Index"}`; checked on every header cell across all sheets.
- HS codes and other code-like columns (`HS_Code`, `Código`, `Código
  adicional`, `Código de cuota`) are written as Python `str` end-to-end
  (SQLite `TEXT` column → in-memory `dict` → openpyxl cell), so leading
  zeros are never lost, and are additionally given the `@` (text) number
  format so Excel never reinterprets them as numbers/scientific notation.
- Atomic write: the workbook is saved to a `.tmp` file, reopened with
  `openpyxl.load_workbook` to confirm it isn't corrupted, structurally
  validated (`validate_workbook_structure`), and only then moved into place
  with `os.replace`.

## Shared styling (`exporters/styles.py`)

| Aspect | Value |
| --- | --- |
| Header fill | solid `4472C4` (the blue used throughout the pre-migration, screenshot-validated implementation) |
| Header font | bold, white (`FFFFFF`) |
| Header row height | 22 points (`HEADER_ROW_HEIGHT`) |
| Data row height | explicit, `DATA_LINE_HEIGHT` (25 points) multiplied by the estimated number of wrapped lines in the row. Never left implicit: Excel (15 pt) and LibreOffice (~12.8 pt) use different defaults, which would make the same file render with different geometry in each engine. The 25 pt value was calibrated by sweeping 20/22/24/25/26/27/28 pt and measuring the four real captures; 25 pt maximized the worst-sheet SSIM. |
| Border (header + data) | thin, all four sides, default (black) color |
| Header alignment | horizontal `center`, vertical `center`, `wrap_text=True` |
| Data alignment | vertical `top`, `wrap_text=True` |
| Column width | autosized from the longest value in that column, clamped to `[12, 60]` characters (+2 padding) |
| Freeze panes | first row below the header block (`A2` for single-header sheets, `A3` for the two-row-header sheets) |
| Autofilter | covers the full header + data range of each sheet |
| Number format | `@` (text) on every `HS_Code`/`Código*` column, for header and data rows alike |

## Sheet layouts

### 1. Derechos e impuestos

The fixture used by the visual comparison (`scripts/sample_workbook.py`)
reproduces the values visible in the capture: two data rows, empty `Código
adicional`/`Código de cuota`, and no `DAI_CU` value for the first code. The
`Código` column still shows every duty code present in a row (`DAI | IVA`),
which the capture does not; that content difference is asserted structurally
instead of visually.

One header row (freeze panes `A2`, autofilter starts at row 1), matching the
real screenshot. Dynamic columns retain their explicit duty/agreement names
(`DAI_GENERAL`, `IVA_GENERAL`, `DAI_MX`, and so on); no grouped header merges
are introduced.

Column order:

1. `HS_Code` (fixed, merged)
2. `Status` (fixed, merged)
3. `Overall_Status` (fixed, merged)
4. `Código` (fixed, merged — pipe-joined list of codes present in the row)
5. One column per distinct `(duty/tax code, agreement)` pair found in the
   data, ordered with `TRATAMIENTO GENERAL` first, followed by other
   agreements in the order hinted by `DUTY_GROUP_ORDER_HINT`. Agreement names
   are normalized and matched to SAT's canonical agreement mapping (for
   example, SAT's `ADAE` agreement is exported as `DAI_AE`); any unknown
   agreement with an explicit trailing code uses that code, and otherwise uses
   a stable name-based suffix.
6. `Código adicional` (fixed, merged)
7. `Código de cuota` (fixed, merged)

If a code has no extracted rows at all, a single row with blank dynamic
values is still emitted so the code is traceable.

### 2. Nomenclatura

Two header rows (freeze panes `A3`, autofilter starts at row 2):

- **Row 1**: `HS_Code`, `Status`, `Overall_Status`, `Sección`, `Capítulo:`,
  `Fecha inicio de vigencia:`, `Fecha fin de vigencia:`, `Códigos
  adicionales` each merged vertically across rows 1-2; then a single merged
  `Unidades de medida` super-header spanning the last two columns
  (`I1:J1`).
- **Row 2**: blank under the merged single columns; `Código` and
  `Descripción` under `Unidades de medida`.

One row is emitted per unit-of-measure record for a code (so a code with two
units produces two rows, repeating the scalar fields); a code with no unit
rows still emits one row with blank `Código`/`Descripción`.

### 3. Restricciones

Single header row (freeze panes `A2`, autofilter `A1:H…`):

`HS_Code`, `Status`, `Overall_Status`, `Código`, `Descripción`, `Código
adicional`, `Valor`, `Código de cuota`.

When the `TRATAMIENTO GENERAL` restrictions table has no rows for a code, a
single row is still emitted with blank `Código`/`Descripción`/`Código
adicional`/`Valor`/`Código de cuota` and `Status` carrying the section's
explicit "no data" status (never silently omitted).

### 4. Cuotas

Single header row (freeze panes `A2`, autofilter `A1:D…`):

`HS_Code`, `Status`, `Overall_Status`, `TRATAMIENTO GENERAL`.

The `TRATAMIENTO GENERAL` column holds the quota message(s) for the code,
newline-joined when there are several. When the portal reports no
quotas/contingents, the cell contains exactly:

```
No se han encontrado cuotas/contingentes para el inciso consultado
```

## Visual comparison

See `scripts/compare_excel_visual.py` (module docstring) for the full,
reproducible render pipeline (LibreOffice headless → PDF → `pdftoppm` →
PNG at 200 dpi, one page per sheet), `scripts/visual_normalization.py` for the
non-destructive normalization (RGBA flattening, uniform-margin trimming,
proportional scaling, white padding and a bounded alignment search) and
`tests/visual/test_visual_regression.py` for the pytest integration. Both
resolve the real display-name aliases and never substitute generated images as
references. They self-skip only when local rendering tools, Python
dependencies, screenshots or the approved baseline are missing.

Two modes exist and answer different questions:

| Mode | Command | Reference | Thresholds |
| --- | --- | --- | --- |
| Design | `python scripts/compare_excel_visual.py --mode design` | `references/*.png` (Excel captures) | mean ≤ 0.18, SSIM ≥ 0.35 |
| Baseline | `python scripts/compare_excel_visual.py --mode baseline` | `tests/visual/baselines/libreoffice/*.png` | mean ≤ 0.01, SSIM ≥ 0.98 |

The baseline is regenerated only by `python scripts/update_visual_baseline.py
--confirm`, which also writes a `manifest.json` with the LibreOffice/poppler
versions, platform, DPI, per-sheet dimensions, SHA-256 hashes, generation date
and the command used. A missing, incomplete, tampered or DPI-incompatible
baseline fails with an explicit message instead of being silently rebuilt.

A negative control
(`test_material_regression_fails_the_baseline_comparison`) repaints the rights
header red and asserts that the baseline comparison fails (measured
mean 0.1049 / SSIM 0.8397 for that sheet, with the other three still at
0.0000/1.0000).

The visual comparison is **supplementary**: it is not a substitute for the
structural assertions in `test_exporters.py` and `output_validator.py`, which
are unconditional and must always pass.
