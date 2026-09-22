"""Main entry point for SAT Tariff Scraper."""

import argparse
import logging
import sys
from pathlib import Path

from config import (
    HS_CODES,
    LOG_FORMAT,
    LOG_LEVEL,
    MAX_RETRIES,
    OUTPUT_FILE,
    REQUEST_DELAY,
    RETRY_BACKOFF,
    STATE_FILE_SUFFIX,
)
from sat_scraper import SATTariffScraper

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format=LOG_FORMAT,
    handlers=[
        logging.FileHandler("scraper.log"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)


def load_hs_codes_from_file(file_path: str):
    """Load HS codes from a file (one per line)."""
    try:
        path = Path(file_path)
        if not path.exists():
            logger.error("File not found: %s", file_path)
            return None

        with path.open("r", encoding="utf-8") as file_handle:
            lines = [line.strip() for line in file_handle if line.strip()]

        # Spreadsheet exports usually keep a header row (e.g. "number"). HS codes
        # are always digit strings, so treat anything else as a non-code entry.
        codes = [line for line in lines if line.isdigit()]
        for skipped in (line for line in lines if not line.isdigit()):
            logger.warning("Skipping non-numeric entry in %s: %r", file_path, skipped)

        logger.info("Loaded %d HS codes from %s", len(codes), file_path)
        return codes
    except Exception as exc:
        logger.error("Error loading HS codes from file: %s", exc)
        return None


def build_argument_parser():
    """Create the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Scrape SAT tariff data for the provided HS codes."
    )
    parser.add_argument(
        "hs_codes_file",
        nargs="?",
        help="Optional text file containing one HS code per line.",
    )
    parser.add_argument(
        "output_file",
        nargs="?",
        default=OUTPUT_FILE,
        help=f"Excel output file path (default: {OUTPUT_FILE}).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from the saved state file and skip only previously successful HS codes.",
    )
    parser.add_argument(
        "--state-file",
        help="Path to the JSON state file used for resumable processing.",
    )
    parser.add_argument(
        "--delay-between-codes",
        type=float,
        default=REQUEST_DELAY,
        help=f"Pause in seconds between HS codes (default: {REQUEST_DELAY}).",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=MAX_RETRIES,
        help=f"Retries for transient per-code failures (default: {MAX_RETRIES}).",
    )
    parser.add_argument(
        "--retry-backoff",
        type=float,
        default=RETRY_BACKOFF,
        help=f"Base backoff in seconds between retries (default: {RETRY_BACKOFF}).",
    )
    return parser


def default_state_file_for_output(output_file: str) -> str:
    """Build the default state file path for an output workbook."""
    return f"{output_file}{STATE_FILE_SUFFIX}"


def main(argv=None):
    """Main function."""
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    logger.info("=" * 60)
    logger.info("SAT Tariff Scraper - Starting")
    logger.info("=" * 60)

    hs_codes = HS_CODES
    if args.hs_codes_file:
        loaded_codes = load_hs_codes_from_file(args.hs_codes_file)
        if loaded_codes is None:
            sys.exit(1)
        hs_codes = loaded_codes

    output_file = args.output_file
    state_file = args.state_file or default_state_file_for_output(output_file)

    if args.delay_between_codes < 0:
        parser.error("--delay-between-codes must be zero or greater")
    if args.max_retries < 0:
        parser.error("--max-retries must be zero or greater")
    if args.retry_backoff < 0:
        parser.error("--retry-backoff must be zero or greater")
    if not hs_codes and not args.hs_codes_file:
        logger.error(
            "No HS codes provided. Usage: python main.py [hs_codes_file.txt] [output_file.xlsx]"
        )
        sys.exit(1)

    logger.info("HS Codes to process: %d", len(hs_codes))
    for code in hs_codes:
        logger.info("  - %s", code)
    logger.info("Output file: %s", output_file)
    logger.info("State file: %s", state_file)
    logger.info("Resume mode: %s", "enabled" if args.resume else "disabled")
    logger.info("Delay between codes: %s seconds", args.delay_between_codes)
    logger.info("Max retries per code: %s", args.max_retries)
    logger.info("Retry backoff: %s seconds", args.retry_backoff)

    # Run scraper
    try:
        scraper = SATTariffScraper(
            delay_between_codes=args.delay_between_codes,
            max_retries=args.max_retries,
            retry_backoff=args.retry_backoff,
        )
        scraper.run(
            hs_codes,
            output_file=output_file,
            resume=args.resume,
            state_file=state_file,
        )
        logger.info("=" * 60)
        logger.info("Scraping completed successfully!")
        logger.info("Results saved to: %s", output_file)
        logger.info("=" * 60)
    except Exception as exc:
        logger.error("Fatal error: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
