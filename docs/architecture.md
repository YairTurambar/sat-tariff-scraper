# Architecture

## Package layout

- `src/sat_tariff/config.py` loads defaults and optional environment overrides.
- `src/sat_tariff/validation/input_validator.py` validates `HS_codes.txt`.
- `src/sat_tariff/storage.py` persists resumable code and per-section row data in SQLite.
- `src/sat_tariff/checkpoint.py` determines which section to process next.
- `src/sat_tariff/browser.py` lazily imports Playwright and launches a persistent context, trying explicit path, channel, already-installed managed binary and auto-detected system browsers in that order without downloading anything.
- `src/sat_tariff/browser_discovery.py` locates system Chrome/Edge/Chromium and the Playwright-managed binary offline.
- `src/sat_tariff/navigation.py` coordinates browser actions, manual CAPTCHA pauses, extractors, evidence capture, and state transitions.
- `src/sat_tariff/extractors/` contains pure HTML parsers.
- `src/sat_tariff/exporters/` builds the styled Excel workbook from SQLite rows.
- `src/sat_tariff/validation/output_validator.py` validates workbook structure.

## Flow

1. Validate `HS_codes.txt`
2. Upsert HS codes into SQLite
3. Open the SAT portal in Playwright
4. Pause for manual CAPTCHA resolution when needed
5. Search each code and extract sections in order:
   - rights
   - nomenclature
   - restrictions
   - quotas
6. Persist structured rows after each section
7. Export workbook from SQLite

## Resume model

Processing state is stored per HS code. Completed/permanent failures are not resumed. Section tables contain the raw rows required to rebuild the workbook without reopening the portal.
