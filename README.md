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
playwright install  # optional when a system Chrome/Edge/Chromium is installed
```

`playwright install` downloads browser binaries and may need to be run outside restricted CI/sandbox
environments. When that download is blocked or times out (the CDN redirects to
`storage.googleapis.com`), skip it and use a browser already installed on the system — see
[Using a system browser](#using-a-system-browser-without-downloading-chromium).

## Using a system browser without downloading Chromium

Check the environment first; `doctor` is offline, never opens the portal and never downloads a browser:

```bash
python -m sat_tariff doctor
```

Force Google Chrome (PowerShell):

```powershell
$env:SAT_BROWSER_CHANNEL="chrome"
python -m sat_tariff doctor
python -m sat_tariff run
```

Or point to the executable explicitly:

```powershell
$env:SAT_BROWSER_EXECUTABLE_PATH="C:\Program Files\Google\Chrome\Application\chrome.exe"
python -m sat_tariff doctor
python -m sat_tariff run
```

Microsoft Edge works as well on Windows:

```powershell
$env:SAT_BROWSER_CHANNEL="msedge"
```

Launch precedence is unambiguous:

1. `SAT_BROWSER_EXECUTABLE_PATH`, when configured (a configured path that does not exist is a
   configuration error and is never silently ignored);
2. `SAT_BROWSER_CHANNEL`, when configured;
3. the Playwright-managed binary, but only when it is already installed;
4. an auto-detected system browser, when `SAT_BROWSER_FALLBACK_TO_SYSTEM=true`.

The managed binary is only attempted when it is already present on disk, so `run` never triggers a
browser download and never waits through repeated download timeouts.

`PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT` only enlarges the download timeout; it does not fix a
blocked domain. Do not disable TLS verification, firewalls or corporate controls to work around it.

## GitHub Copilot cloud agent limitation

The GitHub Copilot agent/app can install the project, run the offline commands and modify the code.
A real `run` needs a **visible** browser and a human solving the CAPTCHA. If the cloud environment
provides no interactive desktop/GUI, using a system Chrome avoids the download but still does not
make CAPTCHA solving possible there. Perform real runs on a local machine or a remote environment
with an interactive desktop. `SAT_HEADLESS=true` is not a workaround: it contradicts the manual
CAPTCHA flow.

## Configuration

Copy `.env.example` to `.env` if you want to override defaults. Useful settings include:

- `SAT_INPUT_FILE=HS_codes.txt`
- `SAT_SQLITE_DB=sat_tariff.db`
- `SAT_OUTPUT_XLSX=sat_tariff_example.xlsx`
- `SAT_HEADLESS=false`
- `SAT_BROWSER_CHANNEL=` (`chrome`, `msedge`, `chrome-beta`, ...)
- `SAT_BROWSER_EXECUTABLE_PATH=`
- `SAT_BROWSER_FALLBACK_TO_SYSTEM=true`
- `SAT_BROWSER_CANDIDATE_PATHS=` (extra executables, separated by the OS path separator or by commas)
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
python -m sat_tariff doctor
python -m sat_tariff run
python -m sat_tariff resume
python -m sat_tariff retry-failed
```

### Command notes

- `validate-input`: validates `HS_codes.txt` only
- `status`: shows SQLite state counts only
- `export`: creates `sat_tariff_example.xlsx` from SQLite, even when the DB only has headers/no rows
- `doctor`: offline browser preflight; prints the Python version, Playwright import status, whether the
  Playwright-managed Chromium is present, the system browsers found and the strategy that would be
  used. It exits non-zero when no usable browser exists
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

## Visual comparison (dual reference)

Two different questions are answered by two explicit modes:

| Mode | Compares against | Engine | Tolerance | Purpose |
| --- | --- | --- | --- | --- |
| `design` | `references/*.png` (original Excel screenshots) | Excel capture vs LibreOffice render | tolerant | Is the layout still what a human approved? |
| `baseline` | `tests/visual/baselines/libreoffice/*.png` | LibreOffice vs LibreOffice | strict | Did *our* output change at all? |

`scripts/compare_excel_visual.py` renders a deterministic fixture workbook
(the real exporter with controlled test data — see `scripts/sample_workbook.py`)
with LibreOffice headless → PDF → `pdftoppm` at 200 dpi, one page per sheet.

Install the tooling once:

```bash
pip install -e ".[visual]"                              # Pillow, numpy, scikit-image
sudo apt-get install -y libreoffice-calc poppler-utils  # soffice + pdftoppm
```

Run either mode:

```bash
python scripts/compare_excel_visual.py --mode design
python scripts/compare_excel_visual.py --mode baseline
```

Approve/regenerate the renderer baseline explicitly (never automatic, never as
a side effect of a test):

```bash
python scripts/update_visual_baseline.py --confirm
```

### Normalization

Images are never cropped to the smaller of the pair. `scripts/visual_normalization.py`

1. composites RGBA over white,
2. trims only uniform outer margins (white or the light-grey Excel background),
3. scales both proportionally to a shared width (aspect ratio preserved),
4. pastes both on equally sized **white canvases** (padding instead of cropping),
5. and runs a bounded coarse-to-fine translation search (±12 px) so different
   outer margins do not count as differences.

Every step's dimensions are reported, and normalized pairs plus diff images are
written under `artifacts/visual/` (git-ignored).

### Interpreting the metrics

- **SSIM** (structural similarity, −1…1): 1.0 means structurally identical.
  Across engines (design mode) it stays well below 1.0 even for a correct
  sheet, because fonts, hinting and anti-aliasing differ.
- **Mean absolute difference** (0…1): average per-channel pixel error. It is
  the primary signal for colour/content regressions.

### Measured results

Design mode, real screenshots, LibreOffice 24.2.7.2 + poppler 24.02.0
(thresholds: mean ≤ 0.18, SSIM ≥ 0.35):

| Sheet | mean abs diff (before → after) | SSIM (before → after) |
| --- | --- | --- |
| Derechos e impuestos | 0.2017 → **0.1124** | 0.0762 → **0.4912** |
| Nomenclatura | 0.1540 → **0.0973** | 0.2190 → **0.5391** |
| Restricciones | 0.1805 → **0.1179** | 0.1303 → **0.4775** |
| Cuotas | 0.2593 → **0.1295** | 0.0818 → **0.5341** |

Baseline mode reports `mean=0.0000`, `SSIM=1.0000` for the four sheets, which
*is* pixel equality against the approved LibreOffice baseline. No pixel
equivalence is claimed against the Excel screenshots.

The tests run the same code and skip, with an explicit reason, only when the
tools, the optional dependencies, the screenshots or the baseline are missing:

```bash
python -m pytest tests/visual -v
```

Structural assertions (headers, order, styles, text formats) stay
unconditional in `tests/unit/`.

## Tests

```bash
python -m pytest tests/unit -v
```

Integration/manual tests live under `tests/integration/` and are skipped by default.

## Troubleshooting basics

- `Playwright is not installed`: run `pip install -e .[dev]`
- Browser package imported but no browsers installed: run `python -m sat_tariff doctor`, then either
  `playwright install` or set `SAT_BROWSER_CHANNEL=chrome` / `SAT_BROWSER_EXECUTABLE_PATH=...`
- `validate-input` fails: fix empty input, >500 lines, or suspicious data depending on your chosen policy
- `status` shows nothing: no rows have been stored yet
- `export` creates headers only: the SQLite database does not yet contain scraped rows

See `docs/troubleshooting.md` for more detail.

## Responsible automation

Use this tool only if you are authorized to access and collect data from the SAT portal. Throttle requests responsibly and do not overload the portal. This repository does **not** claim SAT terms of service were reviewed or verified in this environment.
