# Reference screenshots

Place local SAT portal reference screenshots in this directory with these
exact filenames (used by both `scripts/compare_excel_visual.py` and
`tests/visual/test_visual_regression.py`):

- `references/derechos_e_impuestos.png`
- `references/nomenclatura.png`
- `references/restricciones.png`
- `references/cuotas.png`

## Current status: files not available

As of this revision, **none of the four files above are present**. They were
referenced only as inline placeholders in two different task descriptions;
in both sessions, no attachment, binary image payload, or file path for them
was retrievable anywhere in the sandboxed environment (filesystem,
attachment store, session database were all checked). This is documented
precisely here rather than fabricating a format or claiming a comparison
that did not happen.

Because of this, the workbook layout in
`docs/excel-format-specification.md` was derived from the project's
pre-migration implementation (which earlier, merged PRs describe as having
been matched against the real screenshots) and from the literal textual
requirements in the task description — not from direct pixel inspection.
`tests/visual/test_visual_regression.py` is skipped with an explicit reason
whenever these files are missing, so this gap is visible in CI/test output
rather than silently ignored.

## Adding the real screenshots later

1. Save each screenshot under this directory with the exact filename above
   (PNG, full worksheet view including header rows).
2. Re-read them against `docs/excel-format-specification.md` and correct any
   discrepancy (exact header texts, column order/count, merges, fill/font
   colors, borders, alignment/wrap, approximate column/row sizes, filters,
   freeze panes).
3. Run the reproducible render/compare pipeline:

   ```bash
   pip install -e ".[visual]"
   python scripts/compare_excel_visual.py
   ```

   This exports a deterministic fixture workbook, renders each sheet to PNG
   with LibreOffice + poppler, and prints a mean-pixel-difference/SSIM table
   per sheet, writing diff images under `artifacts/visual/` (git-ignored).
4. Run `python -m pytest tests/visual -v` — it will now execute instead of
   skipping, and fail on a real regression.
5. Tighten the tolerances in `scripts/compare_excel_visual.py` once an actual
   calibration baseline exists.
