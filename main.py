"""
Main entry point for SAT Tariff Scraper
"""

import sys
import logging
from pathlib import Path
from sat_scraper import SATTariffScraper
from config import HS_CODES, LOG_LEVEL, LOG_FORMAT, OUTPUT_FILE

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format=LOG_FORMAT,
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def load_hs_codes_from_file(file_path: str) -> list:
    """Load HS codes from a file (one per line)"""
    try:
        if not Path(file_path).exists():
            logger.error(f"File not found: {file_path}")
            return []
        
        with open(file_path, 'r') as f:
            codes = [line.strip() for line in f if line.strip()]
        
        logger.info(f"Loaded {len(codes)} HS codes from {file_path}")
        return codes
    except Exception as e:
        logger.error(f"Error loading HS codes from file: {e}")
        return []


def main():
    """Main function"""
    logger.info("=" * 60)
    logger.info("SAT Tariff Scraper - Starting")
    logger.info("=" * 60)
    
    # Check for command line arguments
    hs_codes = HS_CODES
    output_file = OUTPUT_FILE
    
    if len(sys.argv) > 1:
        # Load from file if provided
        loaded_codes = load_hs_codes_from_file(sys.argv[1])
        if loaded_codes:
            hs_codes = loaded_codes
    
    if len(sys.argv) > 2:
        output_file = sys.argv[2]
    
    if not hs_codes:
        logger.error("No HS codes provided. Usage: python main.py [hs_codes_file.txt] [output_file.xlsx]")
        sys.exit(1)
    
    logger.info(f"HS Codes to process: {len(hs_codes)}")
    for code in hs_codes:
        logger.info(f"  - {code}")
    logger.info(f"Output file: {output_file}")
    
    # Run scraper
    try:
        scraper = SATTariffScraper()
        scraper.run(hs_codes, output_file)
        logger.info("=" * 60)
        logger.info("Scraping completed successfully!")
        logger.info(f"Results saved to: {output_file}")
        logger.info("=" * 60)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
