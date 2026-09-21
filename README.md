# sat-tariff-scraper

Automated scraper for Guatemalan SAT tariff (arancel integrado) data extraction to Excel.

## Output workbook

The generated Excel file keeps SAT data in four separate worksheets:

- `Derechos e impuestos`
- `Nomenclatura`
- `Restricciones`
- `Cuotas`

Each worksheet contains:

- `HS_Code`
- `Status`
- `Overall_Status`
- all fields extracted for that SAT section

If a section has no data or cannot be extracted for a code, the worksheet is still created and the row is written with `HS_Code` and `Status`.

## CAPTCHA handling

CAPTCHA solving remains manual. When SAT shows a CAPTCHA, solve it in the browser window and the scraper will continue after the CAPTCHA field disappears.
