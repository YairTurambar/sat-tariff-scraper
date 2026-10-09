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

## `playwright install chromium` times out or is blocked

The Playwright CDN redirects to `storage.googleapis.com`. In sandboxes such as the GitHub Copilot
cloud agent that host is blocked or too slow, so every attempt exhausts
`PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT`. Raising that timeout does not fix a blocked domain, and
disabling TLS verification, firewalls or corporate controls is not an acceptable workaround.

The download is optional. Use a Chrome/Edge/Chromium already installed on the machine:

```bash
python -m sat_tariff doctor        # offline preflight, no download, no portal, no CAPTCHA
```

```powershell
$env:SAT_BROWSER_CHANNEL="chrome"   # or "msedge"
python -m sat_tariff run
```

```powershell
$env:SAT_BROWSER_EXECUTABLE_PATH="C:\Program Files\Google\Chrome\Application\chrome.exe"
python -m sat_tariff run
```

`run` only tries the Playwright-managed binary when it already exists on disk, so it fails fast
instead of retrying downloads.

## "No usable browser was found."

No managed binary, no configured channel/path and no system browser was detected. Set
`SAT_BROWSER_CHANNEL=chrome`, set `SAT_BROWSER_EXECUTABLE_PATH=...`, install Chrome/Edge/Chromium,
or (only if the download works in your network) run `playwright install chromium`. Check
`SAT_BROWSER_FALLBACK_TO_SYSTEM=true` if auto-detection is expected.

## "SAT_BROWSER_EXECUTABLE_PATH points to ... which is not an existing file"

Explicit configuration is never ignored silently. Correct the path, use `SAT_BROWSER_CHANNEL`, or
unset the variable to auto-detect a system browser.

## Running from the GitHub Copilot cloud agent

The agent can install the project, run the offline commands (`validate-input`, `status`, `export`,
`doctor`) and change the code. It cannot complete a real `run`: the flow needs a visible browser
and a human solving the CAPTCHA. Using a system Chrome avoids the download but does not provide an
interactive desktop. Run the scraper locally or on a remote machine with a GUI. Do not set
`SAT_HEADLESS=true` to bypass this.

## CAPTCHA blocks progress

This project intentionally stops for manual CAPTCHA solving. Keep the browser visible, solve **and
submit** the challenge there and do nothing in the terminal: the application polls the DOM and
restarts the extraction by itself when `frmBuscar:txtCodigo` becomes visible and enabled.

## The extraction does not continue after solving the CAPTCHA

1. Confirm the query form really became usable in the browser (the HS field must be editable).
2. Increase `SAT_CAPTCHA_TIMEOUT_SECONDS` if you need more time; the default is 300 seconds.
3. Inspect the newest `artifacts/<code>-<section>-<timestamp>.json`. It records the current URL,
   the frame URLs and whether the CAPTCHA, the `frmBuscar` form and the HS input were detected.
   The matching `.png` and sanitized `.html` files show what the browser displayed.
4. Typical causes: the landing page was loaded instead of `SAT_CONSULTA_URL`, the CAPTCHA was still
   active, the SAT portal returned an error page, or a selector became obsolete.
5. Nothing is lost: already stored sections stay in SQLite, the code remains in `captcha_required`
   or `retryable_error` and `python -m sat_tariff resume` continues where it stopped.

## `export` exits with code 3 / warnings about `Tabla 14`, `Tabla 17`

**Root cause**: an older version of the extractor fell back to the position of the table in the HTML
(`Tabla N`) when it could not find a visible title, and persisted that label as `agreement_name`.
A table number is not a trade agreement, so the exporter cannot rebuild the real agreement and the
rate would otherwise be dropped silently.

**How to identify a contaminated database**:

```bash
python -m sat_tariff repair-rights --dry-run
```

It prints every HS code and positional label found in `rights_taxes_rows`. `python -m sat_tariff
export` reports the same codes on stderr and exits with code `3`.

**How to repair it**:

```bash
python -m sat_tariff repair-rights   # deletes only the corrupted rights rows and reopens checkpoints
python -m sat_tariff resume          # re-extracts the rights section from the portal
python -m sat_tariff export          # must now exit 0
```

Nomenclature, restrictions and quotas rows are untouched by the repair.

**How to verify the result**: the first row of the `Derechos e impuestos` sheet must show
`DAI_GENERAL`, `IVA_GENERAL` and one semantic column per agreement (`DAI_BZ`, `DAI_MX`, …). No
`DAI_TABLA_*` or `IVA_TABLA_*` header is accepted; `validate_workbook_structure()` rejects the
workbook if one appears.

## A section is announced as "incompleto"

`parse_rights_taxes()` could not resolve the official agreement name of one of the rates tables and
refused to store a positional identity. The message contains the duty codes and an HTML snippet as
evidence. Re-run the section (`python -m sat_tariff resume`); if it persists, the portal markup
changed and `resolve_rights_table_agreement_name()` needs a new structural strategy.

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
