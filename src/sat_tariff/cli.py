"""Command-line interface for the SAT tariff application."""

from __future__ import annotations

import argparse
from pathlib import Path
import platform
import sys

from .config import ConfigurationError, load_config
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
    prepare_parser = subparsers.add_parser(
        "prepare-batches",
        help="Split the master HS code file into batch files of at most 500 codes plus a manifest",
    )
    prepare_parser.add_argument("--batch-size", type=int, default=None, help="Codes per batch (1-500)")
    prepare_parser.add_argument("--directory", default=None, help="Directory for the generated batches")
    run_batches_parser = subparsers.add_parser(
        "run-batches",
        help="Process every prepared batch in one run, with a single persistent browser session",
    )
    run_batches_parser.add_argument("--directory", default=None, help="Directory holding the prepared batches")
    resume_batches_parser = subparsers.add_parser(
        "resume-batches",
        help="Resume every prepared batch from SQLite state, with a single persistent browser session",
    )
    resume_batches_parser.add_argument("--directory", default=None, help="Directory holding the prepared batches")
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
        print(
            "Para archivos maestros con más de 500 códigos usa "
            "'python -m sat_tariff prepare-batches' y luego 'python -m sat_tariff run-batches'.",
            file=sys.stderr,
        )
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
        print(
            "Para archivos maestros con más de 500 códigos usa "
            "'python -m sat_tariff prepare-batches' y luego 'python -m sat_tariff run-batches'.",
            file=sys.stderr,
        )
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



def cmd_prepare_batches(config, *, batch_size: int | None = None, directory: str | None = None) -> int:
    from .batches import BatchError, prepare_batches

    try:
        manifest = prepare_batches(config, batch_size=batch_size, directory=directory)
    except (BatchError, InputValidationError, OSError) as exc:
        print(f"Batch preparation failed: {exc}", file=sys.stderr)
        return 1
    target_dir = manifest.directory
    print(f"Master file: {manifest.master_file}")
    print(f"Master SHA-256: {manifest.master_sha256}")
    print(f"Total non-empty lines: {manifest.total_lines}")
    print(f"Unique processable codes: {manifest.total_codes}")
    print(f"Duplicates skipped: {len(manifest.duplicates_skipped)}")
    print(f"Suspicious codes ({manifest.invalid_line_policy} policy): {len(manifest.suspicious_codes)}")
    print(f"Batch size: {manifest.batch_size}")
    print(f"Batches created: {len(manifest.batches)} in {target_dir}")
    for batch in manifest.batches:
        print(f"  {batch.number:03d}: {batch.path} ({batch.count} códigos)")
    print(f"Manifest written to {target_dir / 'manifest.json'}")
    print("Ejecuta 'python -m sat_tariff run-batches' y luego 'python -m sat_tariff export'.")
    return 0


def _run_batches_command(config, *, resume: bool = False, directory: str | None = None) -> int:
    from .batches import (
        BatchError,
        build_batch_plans,
        load_batch_entries,
        load_manifest,
        verify_manifest,
    )

    batch_directory = Path(directory) if directory else config.batch_directory
    try:
        manifest = load_manifest(batch_directory)
        verify_manifest(manifest)
        # The policy recorded in the manifest is authoritative: changing
        # SAT_INVALID_LINE_POLICY afterwards must not silently change which
        # codes belong to the prepared set.
        loaded = load_batch_entries(manifest)
    except (BatchError, InputValidationError, OSError) as exc:
        print(f"Batch manifest error: {exc}", file=sys.stderr)
        return 1

    storage = Storage(config.sqlite_db)
    try:
        all_entries = []
        seen = set()
        for _batch, entries in loaded:
            for entry in entries:
                if entry.normalized_code in seen:
                    continue
                seen.add(entry.normalized_code)
                all_entries.append(entry)
        # Manifest codes missing from SQLite are registered as pending without
        # touching the state or the sections of codes stored by previous runs.
        storage.register_codes([(entry.normalized_code, entry.raw_code) for entry in all_entries])
        states = storage.get_states(entry.normalized_code for entry in all_entries)
        finished = {ProcessingState.completed.value, ProcessingState.permanent_error.value}
        already_completed = sum(1 for entry in all_entries if states.get(entry.normalized_code) in finished)
        pending_codes = {
            entry.normalized_code
            for entry in all_entries
            if states.get(entry.normalized_code) not in finished
        }
        plans = build_batch_plans(loaded, pending_codes)
        total_pending = sum(len(plan.entries) for plan in plans)

        print(f"Lotes en el manifiesto: {len(manifest.batches)}")
        print(f"Total de códigos: {len(all_entries)}")
        print(f"Completados previamente: {already_completed}")
        if not plans:
            print("Processed 0 HS codes.")
            print("No quedan códigos pendientes; el navegador no se abrió.")
            return 0

        mode = "resume-batches" if resume else "run-batches"
        print(f"{mode}: {total_pending} código(s) pendientes en {len(plans)} lote(s).")
        from .navigation import run_navigation_batches

        try:
            run_navigation_batches(plans, config, storage, force_restart=False)
        finally:
            states_after = storage.get_states(entry.normalized_code for entry in all_entries)
            processed_now = sum(
                1
                for entry in all_entries
                if entry.normalized_code in pending_codes
                and states_after.get(entry.normalized_code) == ProcessingState.completed.value
            )
            remaining = total_pending - processed_now
            print(f"Processed {processed_now} HS codes.")
            print(f"Lotes recorridos: {len(plans)}")
            print(f"Fallidos/pendientes: {remaining}")
            if manifest.duplicates_skipped:
                print(f"Duplicados omitidos al preparar: {len(manifest.duplicates_skipped)}")
            print("Consolida el Excel con 'python -m sat_tariff export'.")
        return 0
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
    try:
        config = load_config()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    commands = {
        "validate-input": lambda: cmd_validate_input(config),
        "status": lambda: cmd_status(config),
        "export": lambda: cmd_export(config),
        "repair-rights": lambda: cmd_repair_rights(config, dry_run=getattr(args, "dry_run", False)),
        "doctor": lambda: cmd_doctor(config),
        "run": lambda: _run_browser_command(config),
        "resume": lambda: _run_browser_command(config, resume_only=True),
        "retry-failed": lambda: _run_browser_command(config, retry_failed=True),
        "prepare-batches": lambda: cmd_prepare_batches(
            config,
            batch_size=getattr(args, "batch_size", None),
            directory=getattr(args, "directory", None),
        ),
        "run-batches": lambda: _run_batches_command(config, directory=getattr(args, "directory", None)),
        "resume-batches": lambda: _run_batches_command(
            config, resume=True, directory=getattr(args, "directory", None)
        ),
    }
    return commands[args.command]()
