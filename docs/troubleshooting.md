# Troubleshooting

## Playwright import errors

Install the package dependencies:

```bash
pip install -e .[dev]
```

If the Python package is installed but the browser binaries are missing, run:

```bash
playwright install
```

## CAPTCHA blocks progress

This project intentionally stops for manual CAPTCHA solving. Keep the browser visible and solve the challenge yourself.

## Export contains headers only

The SQLite database has no stored rows yet, or only empty section data.

## Resume did not restart a completed code

`completed` and `permanent_error` rows are not resumed automatically.

## Visual comparison is skipped

`tests/visual/` self-skips with the exact reason. The usual fixes:

```bash
pip install -e ".[visual]"                              # Pillow, numpy, scikit-image
sudo apt-get install -y libreoffice-calc poppler-utils  # soffice + pdftoppm
```

The design test also needs the four screenshots under `references/`, and the
baseline tests need `tests/visual/baselines/libreoffice/manifest.json`.

## "No renderer baseline manifest" / "does not match its manifest hash"

The approved LibreOffice baseline is missing, incomplete, corrupted or was
generated at a different DPI. Review the design-mode diff first and then
regenerate it deliberately:

```bash
python scripts/compare_excel_visual.py --mode design
python scripts/update_visual_baseline.py --confirm
```

Never regenerate the baseline just to make a failing test pass: a baseline
failure means the rendered workbook changed.

## Baseline comparison fails after an intentional format change

That is the expected signal. Inspect `artifacts/visual/diffs/baseline-*.png`
and the normalized pairs in `artifacts/visual/normalized/`. If the change is
intended, re-approve the baseline with `python scripts/update_visual_baseline.py
--confirm` and commit the regenerated PNGs plus `manifest.json`.

## Design SSIM looks "low" (0.4–0.6)

Design mode compares an Excel screenshot with a LibreOffice render. Different
font rasterization and anti-aliasing cap SSIM well below 1.0 even when the
layout is correct, so the thresholds are tolerant (mean ≤ 0.18, SSIM ≥ 0.35)
and are paired with exact `openpyxl` structural assertions. Use baseline mode
when you need a strict, pixel-level regression signal.
