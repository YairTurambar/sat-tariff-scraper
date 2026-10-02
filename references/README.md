# Reference screenshots

Place local SAT portal reference screenshots in this directory with these
exact filenames (used by both `scripts/compare_excel_visual.py` and
`tests/visual/test_visual_regression.py`):

- `references/derechos_e_impuestos.png`
- `references/nomenclatura.png`
- `references/restricciones.png`
- `references/cuotas.png`

## Current status

The four real screenshots are present using the filenames supplied by the
user. They are PNG/RGBA files with these inspected dimensions:

| Sheet | File | Dimensions |
| --- | --- | --- |
| Derechos e impuestos | `Derechos e impuestos.png` | 1853 × 91 |
| Nomenclatura | `Nomenclatura.png` | 1531 × 124 |
| Restricciones | `Restricciones.png` | 1492 × 147 |
| Cuotas | `Cuotas.png` | 1460 × 137 |

The comparison pipeline accepts these display names as aliases for the
canonical lowercase names above. It never uses generated images as
references.

## Latest offline comparison

Using `scripts/sample_workbook.py`, LibreOffice 24.2.7.2, `pdftoppm
24.02.0`, Pillow, NumPy, and scikit-image:

| Sheet | Mean absolute pixel difference | SSIM | Rendered | Normalized | Result |
| --- | ---: | ---: | --- | --- | --- |
| Derechos e impuestos | 0.2034 | 0.0635 | 1650×1275 | 900×29 | FAIL |
| Nomenclatura | 0.1538 | 0.2199 | 1650×1275 | 900×61 | PASS |
| Restricciones | 0.1801 | 0.1321 | 1650×1275 | 900×50 | PASS |
| Cuotas | 0.2592 | 0.0831 | 1650×1275 | 900×67 | PASS |

Reference dimensions are the dimensions in the table above. The rights sheet
remains below the calibrated SSIM threshold (`0.08`), so the visual test
correctly fails rather than being omitted. The remaining difference is mainly
the compact reference's column/row proportions and LibreOffice-versus-Excel
text rasterization; no exact pixel-equivalence claim is made. Rendered PNGs
and diffs are in `artifacts/visual/`, which is ignored by Git.

## Running the comparison

1. Re-read the screenshots against `docs/excel-format-specification.md` and
   correct any discrepancy (headers, merges, colors, borders, alignment,
   sizes, filters, and freeze panes).
2. Run the reproducible render/compare pipeline:

   ```bash
   pip install -e ".[visual]"
   python scripts/compare_excel_visual.py
   ```

   This exports a deterministic fixture workbook, renders each sheet to PNG
   with LibreOffice + poppler, and prints a mean-pixel-difference/SSIM table
   per sheet, writing diff images under `artifacts/visual/` (git-ignored).
3. Run `python -m pytest tests/visual -v`. It executes when LibreOffice,
   poppler, and the visual Python dependencies are installed.
4. Record per-sheet mean absolute pixel difference, SSIM, source dimensions,
   normalized dimensions, and remaining differences. These are tolerant
   cross-renderer metrics, not pixel-perfect equivalence.
