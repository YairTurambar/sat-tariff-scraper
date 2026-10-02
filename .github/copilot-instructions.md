# Copilot instructions

- Python package lives under `src/sat_tariff/`; prefer small pure functions and stdlib-first code.
- Offline commands (`validate-input`, `status`, `export`) must work without Playwright import side effects.
- Persist scrape state in SQLite via `sat_tariff.storage.Storage` and rebuild Excel from the DB instead of browser state.
- Run `python -m pytest tests/unit -v` before finishing changes.
- Do not add CAPTCHA-solving automation; manual-only flows belong in `captcha.py`.
