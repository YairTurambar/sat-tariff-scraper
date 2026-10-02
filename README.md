# sat-tariff-scraper

Packaged Python application for collecting SAT tariff portal data into a resumable SQLite store and exporting a four-sheet Excel workbook.

> This repository now uses `pyproject.toml` instead of `requirements.txt`. Review and confirm the included MIT `LICENSE` placeholder before publishing.

## Features

- Python 3.11+ `src/` package: `sat_tariff`
- Offline-safe commands: `validate-input`, `status`, `export`
- Browser-backed commands: `run`, `resume`, `retry-failed`
- SQLite persistence for resumable section-by-section scraping
- Pure HTML extractors with pytest coverage
- Manual-only CAPTCHA handling
- Rebuildable Excel output with four sheets:
  - `Derechos e impuestos`
  - `Nomenclatura`
  - `Restricciones`
  - `Cuotas`

## Installation

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
playwright install
```

`playwright install` downloads browser binaries and may need to be run outside restricted CI/sandbox environments.

## Configuration

Copy `.env.example` to `.env` if you want to override defaults. Useful settings include:

- `SAT_INPUT_FILE=HS_codes.txt`
- `SAT_SQLITE_DB=sat_tariff.db`
- `SAT_OUTPUT_XLSX=sat_tariff_example.xlsx`
- `SAT_HEADLESS=false`
- `SAT_INVALID_LINE_POLICY=skip`

Without a `.env`, offline commands still work with defaults.

## Input file

`HS_codes.txt` should contain 1-500 non-empty lines. Example values shipped here are fictional 10-digit numeric strings starting with `9999`.

Validation rules:

- preserves leading zeroes
- detects duplicates and processes each unique code once
- flags suspicious formats (non-digits or length outside 4-10)
- honors `SAT_INVALID_LINE_POLICY=skip|process`

## CLI usage

```bash
python -m sat_tariff validate-input
python -m sat_tariff status
python -m sat_tariff export
python -m sat_tariff run
python -m sat_tariff resume
python -m sat_tariff retry-failed
```

### Command notes

- `validate-input`: validates `HS_codes.txt` only
- `status`: shows SQLite state counts only
- `export`: creates `sat_tariff_example.xlsx` from SQLite, even when the DB only has headers/no rows
- `run`: validates input, opens Playwright, searches codes, persists section data
- `resume`: processes unfinished codes from SQLite
- `retry-failed`: resets retryable/CAPTCHA-blocked rows and tries them again

## Manual CAPTCHA flow

CAPTCHA handling is manual-only.

1. Run `python -m sat_tariff run`
2. When the portal shows a CAPTCHA, solve it in the visible browser window
3. Return to the terminal and press Enter to let the scraper poll again
4. The scraper continues only after the DOM no longer shows the CAPTCHA input

No OCR, no external solving service, and no automatic bypass are implemented.

## Resume and export

- Scrape progress is stored in `sat_tariff.db`
- Per-section raw rows are stored so Excel can be regenerated without re-scraping
- Existing output workbooks are backed up before overwrite when `SAT_BACKUP_OUTPUT=true`

## Reference screenshots

Expected local screenshot filenames are documented in `references/README.md`:

- `references/derechos_e_impuestos.png`
- `references/nomenclatura.png`
- `references/restricciones.png`
- `references/cuotas.png`

The four real files are present under `references/` using their original
display names. The comparison code resolves those names to the canonical
lowercase mapping and never compares a workbook against generated output.
Their inspected dimensions are recorded in `references/README.md`.

## Visual comparison

`scripts/compare_excel_visual.py` renders a deterministic fixture workbook
(the real exporter, controlled test data — see `scripts/sample_workbook.py`)
to PNG using LibreOffice headless + poppler, normalizes each rendered sheet
and its matching `references/*.png` (trims whitespace, rescales to a common
width), and reports a tolerant mean-pixel-difference and SSIM score per
sheet:

```bash
pip install -e ".[visual]"          # Pillow, numpy, scikit-image
sudo apt-get install -y libreoffice-calc poppler-utils  # soffice + pdftoppm
python scripts/compare_excel_visual.py
```

Diff images are written under `artifacts/visual/` (git-ignored). The same
logic runs as `tests/visual/test_visual_regression.py`:

```bash
python -m pytest tests/visual -v
```

The test skips with an explicit reason only when local rendering tools or
Python dependencies are unavailable. With them installed, it compares all
four real screenshots and reports mean absolute pixel difference, SSIM,
reference/rendered dimensions, and normalized dimensions. These are tolerant
cross-renderer metrics; only identical pixel arrays justify an exact
pixel-equivalence claim. In the latest offline run, all four sheets passed; Derechos e impuestos
reported SSIM 0.0762 against the calibrated 0.07 threshold. The complete measured table and remaining
limitation are in `references/README.md`. Structural assertions remain
unconditional.

## Tests

```bash
python -m pytest tests/unit -v
```

Integration/manual tests live under `tests/integration/` and are skipped by default.

## Troubleshooting basics

- `Playwright is not installed`: run `pip install -e .[dev]`
- Browser package imported but no browsers installed: run `playwright install`
- `validate-input` fails: fix empty input, >500 lines, or suspicious data depending on your chosen policy
- `status` shows nothing: no rows have been stored yet
- `export` creates headers only: the SQLite database does not yet contain scraped rows

See `docs/troubleshooting.md` for more detail.

## Responsible automation

Use this tool only if you are authorized to access and collect data from the SAT portal. Throttle requests responsibly and do not overload the portal. This repository does **not** claim SAT terms of service were reviewed or verified in this environment.
