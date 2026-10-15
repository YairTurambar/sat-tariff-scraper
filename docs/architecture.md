# Architecture

## Package layout

- `src/sat_tariff/config.py` loads defaults and optional environment overrides.
- `src/sat_tariff/validation/input_validator.py` validates `HS_codes.txt`.
- `src/sat_tariff/storage.py` persists resumable code and per-section row data in SQLite.
- `src/sat_tariff/checkpoint.py` determines which section to process next.
- `src/sat_tariff/batches.py` splits a master HS code file into batch files of at most `MAX_LINES` codes and writes/validates the versioned `manifest.json`. It is pure and offline.
- `src/sat_tariff/browser.py` lazily imports Playwright and launches a persistent context, trying explicit path, channel, already-installed managed binary and auto-detected system browsers in that order without downloading anything.
- `src/sat_tariff/browser_discovery.py` locates system Chrome/Edge/Chromium and the Playwright-managed binary offline.
- `src/sat_tariff/navigation.py` coordinates browser actions, manual CAPTCHA pauses, extractors, evidence capture, and state transitions.
- `src/sat_tariff/extractors/` contains pure HTML parsers.
- `src/sat_tariff/exporters/` builds the styled Excel workbook from SQLite rows.
- `src/sat_tariff/validation/output_validator.py` validates workbook structure.

## Flow

1. Validate `HS_codes.txt`
2. Upsert HS codes into SQLite
3. Open the direct SAT query page (`SAT_CONSULTA_URL`) once per session in Playwright
4. Pause for manual CAPTCHA resolution when needed, polling the DOM until the query is enabled
5. Search each code (reusing the same session) and extract sections in order, each one submitted
   to a temporary tab through `form.target` so the validated form stays on the main tab:
   - rights
   - nomenclature
   - restrictions
   - quotas
6. Persist structured rows after each section
7. Export workbook from SQLite

## Batch flow (`prepare-batches` / `run-batches` / `resume-batches`)

1. `prepare-batches` validates the master file (no per-file limit applied to the master itself),
   drops global duplicates, splits the codes into deterministic `HS_codes_NNN.txt` files of at most
   `SAT_BATCH_SIZE` (<= `MAX_LINES`) codes, re-validates each generated file with the regular
   validator and writes `manifest.json` atomically.
2. `run-batches`/`resume-batches` load the manifest, verify the SHA-256 of the master file and of
   every batch, register missing codes in SQLite without resetting existing state, and compute the
   pending set from SQLite.
3. `navigation.run_navigation_batches()` creates **one** `BrowserSession` and **one**
   `NavigationService`, calls `open_portal()` once and then `NavigationService.process_batches()`
   walks every batch in order inside the same page/context. No `page.goto()` happens between
   batches, so the JSF form and the solved CAPTCHA survive the batch boundary.
4. Resources are released once, at the end of the command or when a definitive exception propagates.

The manifest is the source of truth for *which* codes must be processed; SQLite remains the source
of truth for *what has already been processed*.

## Resume model

Processing state is stored per HS code. Completed/permanent failures are not resumed. Section tables contain the raw rows required to rebuild the workbook without reopening the portal.
