# Build SAT scraper prompt

Rebuild this repository as a packaged Python 3.11+ application named `sat_tariff`.

Goals:
- replace the legacy Selenium root scripts with `src/` modules,
- validate `HS_codes.txt`,
- persist resumable progress in SQLite,
- parse SAT HTML sections with pure extractor functions,
- export a four-sheet styled workbook with `openpyxl`,
- keep CAPTCHA handling manual-only,
- document architecture, responsible automation, and local reference screenshots,
- cover the offline logic with pytest unit tests.

Constraints:
- no OCR or CAPTCHA bypass,
- lazy-import Playwright for browser-only commands,
- preserve HS code strings exactly,
- store enough section data to regenerate Excel without re-scraping.
