"""Command-line interface for the SAT tariff application."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .config import load_config
from .exporters.excel import export_workbook
from .models import ProcessingState
from .storage import Storage
from .validation.input_validator import InputValidationError, validate_hs_code_file



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m sat_tariff", description="SAT tariff scraper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("validate-input", help="Validate HS_codes.txt without browser dependencies")
    subparsers.add_parser("status", help="Show SQLite processing summary")
    subparsers.add_parser("export", help="Build the Excel workbook from SQLite data")
    subparsers.add_parser("run", help="Validate input and process all HS codes")
    subparsers.add_parser("resume", help="Resume unfinished HS codes from SQLite state")
    subparsers.add_parser("retry-failed", help="Reset retryable/captcha failures and process them again")
    return parser



def _validated_entries(config):
    result = validate_hs_code_file(config.input_file, invalid_policy=config.invalid_line_policy)
    return result.entries, result



def _print_status(storage: Storage) -> None:
    summary = storage.get_status_summary()
    if not summary:
        print("No HS codes stored yet.")
        return
    for state, total in summary.items():
        print(f"{state}: {total}")



def cmd_validate_input(config) -> int:
    try:
        entries, result = _validated_entries(config)
    except InputValidationError as exc:
        print(f"Input validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Valid unique codes: {len(entries)}")
    print(f"Total non-empty lines: {result.total_lines}")
    if result.duplicate_codes:
        print(f"Duplicates skipped: {', '.join(result.duplicate_codes)}")
    if result.suspicious_codes:
        print(f"Suspicious codes ({config.invalid_line_policy} policy): {', '.join(result.suspicious_codes)}")
    return 0



def cmd_status(config) -> int:
    storage = Storage(config.sqlite_db)
    try:
        _print_status(storage)
    finally:
        storage.close()
    return 0



def cmd_export(config) -> int:
    storage = Storage(config.sqlite_db)
    try:
        bundles = storage.load_all_for_export()
    finally:
        storage.close()
    path = export_workbook(bundles, config)
    print(f"Workbook written to {path}")
    return 0



def _run_browser_command(config, *, resume_only: bool = False, retry_failed: bool = False) -> int:
    storage = Storage(config.sqlite_db)
    try:
        entries, result = _validated_entries(config)
        by_code = {entry.normalized_code: entry for entry in entries}
        if retry_failed:
            storage.reset_states([ProcessingState.retryable_error, ProcessingState.captcha_required])
        if resume_only or retry_failed:
            resumable = storage.get_codes_to_resume()
            entries = [by_code[row["code"]] for row in resumable if row["code"] in by_code]
        from .browser import BrowserUnavailableError
        from .navigation import run_navigation

        run_navigation(entries, config, storage, force_restart=False)
        print(f"Processed {len(entries)} HS codes.")
        if result.duplicate_codes:
            print(f"Skipped duplicates: {', '.join(result.duplicate_codes)}")
        return 0
    except InputValidationError as exc:
        print(f"Input validation failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        browser_unavailable = getattr(sys.modules.get("sat_tariff.browser"), "BrowserUnavailableError", None)
        if browser_unavailable and isinstance(exc, browser_unavailable):
            print(str(exc), file=sys.stderr)
            return 2
        print(f"Command failed: {exc}", file=sys.stderr)
        return 1
    finally:
        storage.close()



def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_config()

    commands = {
        "validate-input": lambda: cmd_validate_input(config),
        "status": lambda: cmd_status(config),
        "export": lambda: cmd_export(config),
        "run": lambda: _run_browser_command(config),
        "resume": lambda: _run_browser_command(config, resume_only=True),
        "retry-failed": lambda: _run_browser_command(config, retry_failed=True),
    }
    return commands[args.command]()
