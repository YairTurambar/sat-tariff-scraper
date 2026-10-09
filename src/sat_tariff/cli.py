"""Command-line interface for the SAT tariff application."""

from __future__ import annotations

import argparse
from pathlib import Path
import platform
import sys

from .config import load_config
from .extractors.rights_taxes import is_positional_identity
from .exporters.excel import collect_positional_rights_issues, export_workbook
from .models import ProcessingState
from .storage import Storage
from .validation.input_validator import InputValidationError, validate_hs_code_file



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m sat_tariff", description="SAT tariff scraper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("validate-input", help="Validate HS_codes.txt without browser dependencies")
    subparsers.add_parser("status", help="Show SQLite processing summary")
    subparsers.add_parser("export", help="Build the Excel workbook from SQLite data")
    repair_parser = subparsers.add_parser(
        "repair-rights",
        help="Delete rights rows stored with a positional label ('Tabla N') and reopen their checkpoint",
    )
    repair_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report the affected HS codes without modifying SQLite",
    )
    subparsers.add_parser("doctor", help="Check browser availability offline, without opening the portal")
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
    issues = collect_positional_rights_issues(bundles)
    path = export_workbook(bundles, config)
    print(f"Workbook written to {path}")
    if issues:
        print(
            "Export INCOMPLETO: la base contiene tasas guardadas con etiquetas posicionales "
            "('Tabla N'), que no identifican ningún acuerdo comercial y por lo tanto fueron "
            "omitidas del libro.",
            file=sys.stderr,
        )
        for hs_code, labels in issues.items():
            print(f"  HS {hs_code}: {', '.join(labels)}", file=sys.stderr)
        print(
            "Repara la base con 'python -m sat_tariff repair-rights' y vuelve a extraer con "
            "'python -m sat_tariff resume' antes de usar el archivo.",
            file=sys.stderr,
        )
        return 3
    return 0


def cmd_repair_rights(config, *, dry_run: bool = False) -> int:
    storage = Storage(config.sqlite_db)
    try:
        rows_by_code = storage.get_section_rows_by_code("rights")
        affected = {
            code: sorted(
                {
                    row.get("agreement_name", "")
                    for row in rows
                    if is_positional_identity(row.get("agreement_name", ""))
                }
            )
            for code, rows in rows_by_code.items()
        }
        affected = {code: labels for code, labels in affected.items() if labels}
        if not affected:
            print("No se encontraron filas de 'rights' con identidad posicional.")
            return 0
        for code, labels in affected.items():
            print(f"HS {code}: {', '.join(labels)}")
        if dry_run:
            print(f"{len(affected)} código(s) requieren reextracción de 'rights' (dry-run).")
            return 0
        storage.reset_section(affected, "rights")
    finally:
        storage.close()
    print(
        f"Se eliminaron las filas de 'rights' de {len(affected)} código(s) y se reabrió su checkpoint. "
        "Las secciones Nomenclatura, Restricciones y Cuotas se conservaron. "
        "Ejecuta 'python -m sat_tariff resume' para reextraerlas y luego 'python -m sat_tariff export'."
    )
    return 0



def cmd_doctor(config) -> int:
    from .browser import NO_USABLE_BROWSER_MESSAGE, BrowserConfigurationError, build_launch_strategies
    from .browser_discovery import discover_system_browsers, find_managed_chromium

    print(f"Python: {platform.python_version()} ({sys.executable})")
    try:
        import playwright  # noqa: F401

        try:
            from importlib.metadata import version as package_version

            version = package_version("playwright")
        except Exception:
            version = getattr(playwright, "__version__", "unknown")
        print(f"Playwright import: ok (version {version})")
    except Exception as exc:
        print(f"Playwright import: failed ({exc})", file=sys.stderr)
        print("Install the project dependencies with 'pip install -e .[dev]'.", file=sys.stderr)
        return 1

    managed = find_managed_chromium()
    print(f"Playwright-managed Chromium: {managed if managed else 'not installed (no download attempted)'}")

    system_browsers = discover_system_browsers(extra_candidates=config.browser_candidate_paths)
    if system_browsers:
        print("System browsers found:")
        for path in system_browsers:
            print(f"  - {path}")
    else:
        print("System browsers found: none")

    try:
        strategies = build_launch_strategies(
            config, managed_browser=managed, system_browsers=system_browsers
        )
    except BrowserConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not strategies:
        print(NO_USABLE_BROWSER_MESSAGE, file=sys.stderr)
        return 1

    print(f"Strategy that would be used: {strategies[0].description}")
    if len(strategies) > 1:
        print(f"Fallback strategies available: {len(strategies) - 1}")
    print("A real 'run' still needs a visible browser and manual CAPTCHA solving on an interactive desktop.")
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
        if not entries:
            print("Processed 0 HS codes.")
            return 0
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
        "repair-rights": lambda: cmd_repair_rights(config, dry_run=getattr(args, "dry_run", False)),
        "doctor": lambda: cmd_doctor(config),
        "run": lambda: _run_browser_command(config),
        "resume": lambda: _run_browser_command(config, resume_only=True),
        "retry-failed": lambda: _run_browser_command(config, retry_failed=True),
    }
    return commands[args.command]()
