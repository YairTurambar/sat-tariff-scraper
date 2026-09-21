# SAT Tariff Scraper - Installation & Setup Guide

## Quick Start

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)
- Google Chrome browser
- Git (for cloning the repository)

### Step 1: Clone the Repository
```bash
git clone https://github.com/YairTurambar/sat-tariff-scraper.git
cd sat-tariff-scraper
```

### Step 2: Create Virtual Environment
```bash
# On Windows
python -m venv venv
venv\Scripts\activate

# On macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Configure HS Codes
Edit `config.py` or create a text file with your HS codes (one per line):
```
0101210000
0102210000
0103210000
```

### Step 5: Run the Scraper

**Option A - Simple usage:**
```bash
python main.py
```

**Option B - With external file:**
```bash
python main.py hs_codes.txt output_results.xlsx
```

The generated workbook includes separate worksheets for `Derechos e impuestos`,
`Nomenclatura`, `Restricciones`, and `Cuotas`.

## Project Structure

```
sat-tariff-scraper/
├── sat_scraper.py          # Main scraper class
├── main.py                 # Entry point
├── config.py               # Configuration settings
├── requirements.txt        # Python dependencies
├── test_scraper.py         # Unit tests
├── hs_codes_example.txt    # Example HS codes
├── README.md               # Full documentation
├── SETUP.md               # This file
└── .gitignore             # Git ignore rules
```

## Configuration Options

Edit `config.py` to customize:

```python
# Portal URL
SAT_BASE_URL = "https://portal.sat.gob.gt/portal/arancel-integrado/"

# Browser options
CHROME_OPTIONS = {
    'headless': False,  # Set True to hide browser window
    'no_sandbox': True,
    'disable_dev_shm_usage': True,
}

# Wait times (seconds)
WAIT_TIMEOUT = 15
PAGE_LOAD_DELAY = 3
REQUEST_DELAY = 2

# Output file
OUTPUT_FILE = "sat_tariff_data.xlsx"

# HS Codes to scrape
HS_CODES = ["0101210000"]
```

## Running Tests

```bash
# Run tests
python -m unittest -v
```

## Troubleshooting

### Issue: Chrome driver not found
**Solution:**
```bash
pip install --upgrade webdriver-manager
```

### Issue: Connection timeout
**Solution:** Increase wait times in `config.py`:
```python
WAIT_TIMEOUT = 30  # Increase from 15
REQUEST_DELAY = 5  # Increase from 2
```

### Issue: Portal page structure different
**Solution:** Update XPath selectors in `sat_scraper.py`:
1. Open browser developer tools (F12)
2. Inspect the elements on the SAT portal
3. Update the XPath selectors in the scraper methods

### Issue: Permission denied on venv
**Solution (Linux/Mac):**
```bash
chmod +x venv/bin/activate
```

## Performance Tips

1. **Batch Processing**: Process multiple HS codes in one session
2. **Headless Mode**: Set `'headless': True` in `config.py` for faster execution
3. **Rate Limiting**: Adjust `REQUEST_DELAY` but respect SAT's server

## Security Considerations

⚠️ **Important:**
- This tool is for authorized use only
- Respect SAT's terms of service
- Use appropriate rate limiting
- Do not redistribute scraped data without permission
- Store credentials securely if authentication becomes required

## Logging

Logs are saved to `scraper.log`. To view real-time logs:

```bash
# Follow logs while running
tail -f scraper.log
```

Change log level in `config.py`:
```python
LOG_LEVEL = "DEBUG"  # For detailed debugging
```

## Support

For issues or questions:
1. Check `scraper.log` for error messages
2. Review the README.md for detailed documentation
3. Check GitHub issues in the repository
4. Create a new issue with logs attached

## Next Steps

1. ✅ Installation complete
2. Customize `config.py` with your HS codes
3. Run `python main.py`
4. Check `scraper.log` for execution details
5. Review generated Excel file with results

---

**Last Updated**: 2026-09-11
**Status**: Ready for use
