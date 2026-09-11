"""
Configuration file for SAT Tariff Scraper
"""

# SAT Portal Configuration
SAT_BASE_URL = "https://portal.sat.gob.gt/portal/arancel-integrado/"

# Selenium Configuration
CHROME_OPTIONS = {
    'headless': False,  # Set to True to run in background
    'no_sandbox': True,
    'disable_dev_shm_usage': True,
}

# Wait times (in seconds)
WAIT_TIMEOUT = 15
PAGE_LOAD_DELAY = 3
REQUEST_DELAY = 2

# Excel Configuration
OUTPUT_FILE = "sat_tariff_data.xlsx"
SHEET_NAME = "Tariff Data"

# Header formatting
HEADER_COLOR = "4472C4"
HEADER_TEXT_COLOR = "FFFFFF"

# HS Codes to scrape (can be modified)
HS_CODES = [
    "0101210000",
    # Add more HS codes here
]

# Logging Configuration
LOG_LEVEL = "INFO"
LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
