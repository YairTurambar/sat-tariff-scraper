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
