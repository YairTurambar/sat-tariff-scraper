from pathlib import Path
import sys
import uuid

from sat_tariff import cli
from sat_tariff.storage import Storage



def make_db_path() -> Path:
    path = Path("data") / f"cli-test-{uuid.uuid4().hex}.sqlite3"
    path.unlink(missing_ok=True)
    return path



def test_validate_input_command_does_not_import_playwright(monkeypatch, capsys):
    monkeypatch.setenv("SAT_INPUT_FILE", "HS_codes.txt")
    monkeypatch.setenv("SAT_INVALID_LINE_POLICY", "skip")
    sys.modules.pop("playwright", None)
    rc = cli.main(["validate-input"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Valid unique codes" in out
    assert "playwright" not in sys.modules



def test_status_command_runs_offline_without_importing_playwright(monkeypatch, capsys):
    db_path = make_db_path()
    storage = Storage(db_path)
    storage.close()
    monkeypatch.setenv("SAT_SQLITE_DB", str(db_path))
    sys.modules.pop("playwright", None)
    rc = cli.main(["status"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "No HS codes stored yet." in out
    assert "playwright" not in sys.modules
    db_path.unlink(missing_ok=True)


def test_export_command_runs_offline_without_importing_playwright(monkeypatch, capsys, tmp_path):
    db_path = make_db_path()
    storage = Storage(db_path)
    storage.close()
    monkeypatch.setenv("SAT_SQLITE_DB", str(db_path))
    monkeypatch.setenv("SAT_OUTPUT_XLSX", str(tmp_path / "out.xlsx"))
    sys.modules.pop("playwright", None)
    rc = cli.main(["export"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Workbook written to" in out
    assert "playwright" not in sys.modules
    db_path.unlink(missing_ok=True)


def test_doctor_reports_usable_system_browser(monkeypatch, capsys, tmp_path):
    from sat_tariff import browser_discovery as discovery_module

    executable = tmp_path / "chrome"
    executable.write_text("binary", encoding="utf-8")
    monkeypatch.setattr(discovery_module, "find_managed_chromium", lambda **_: None)
    monkeypatch.setattr(discovery_module, "discover_system_browsers", lambda **_: [str(executable)])

    rc = cli.main(["doctor"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Python:" in out
    assert "Playwright import: ok" in out
    assert "not installed (no download attempted)" in out
    assert str(executable) in out
    assert "Strategy that would be used: system browser" in out


def test_doctor_fails_without_any_browser(monkeypatch, capsys):
    from sat_tariff import browser_discovery as discovery_module

    monkeypatch.setenv("SAT_BROWSER_FALLBACK_TO_SYSTEM", "false")
    monkeypatch.setattr(discovery_module, "find_managed_chromium", lambda **_: None)
    monkeypatch.setattr(discovery_module, "discover_system_browsers", lambda **_: [])

    rc = cli.main(["doctor"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "No usable browser was found." in captured.err
    assert "SAT_BROWSER_CHANNEL=chrome" in captured.err


def test_doctor_reports_invalid_configured_executable(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("SAT_BROWSER_EXECUTABLE_PATH", str(tmp_path / "missing-chrome"))
    rc = cli.main(["doctor"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "SAT_BROWSER_EXECUTABLE_PATH" in captured.err


def _store_rights_rows(db_path: Path, rows):
    storage = Storage(db_path)
    try:
        storage.upsert_code("0101210000", "0101210000")
        storage.save_section_rows("0101210000", "rights", rows, section_status="ok")
        storage.save_section_rows(
            "0101210000",
            "nomenclature",
            [{"record_type": "unit", "unit_code": "KGM", "unit_description": "Kilogramo"}],
            section_status="ok",
        )
    finally:
        storage.close()


def test_export_command_fails_when_sqlite_holds_positional_rights(monkeypatch, capsys, tmp_path):
    db_path = make_db_path()
    _store_rights_rows(
        db_path,
        [
            {"agreement_name": "Tabla 14", "code": "DAI", "value": "10%"},
            {"agreement_name": "TRATAMIENTO GENERAL", "code": "IVA", "value": "12%"},
        ],
    )
    monkeypatch.setenv("SAT_SQLITE_DB", str(db_path))
    monkeypatch.setenv("SAT_OUTPUT_XLSX", str(tmp_path / "out.xlsx"))

    rc = cli.main(["export"])

    captured = capsys.readouterr()
    assert rc == 3
    assert "Export INCOMPLETO" in captured.err
    assert "Tabla 14" in captured.err
    assert "repair-rights" in captured.err
    db_path.unlink(missing_ok=True)


def test_repair_rights_command_resets_only_the_rights_section(monkeypatch, capsys):
    db_path = make_db_path()
    _store_rights_rows(
        db_path,
        [
            {"agreement_name": "Tabla 14", "code": "DAI", "value": "10%"},
            {"agreement_name": "TRATAMIENTO GENERAL", "code": "IVA", "value": "12%"},
        ],
    )
    monkeypatch.setenv("SAT_SQLITE_DB", str(db_path))

    assert cli.main(["repair-rights", "--dry-run"]) == 0
    dry_run_out = capsys.readouterr().out
    assert "dry-run" in dry_run_out

    storage = Storage(db_path)
    try:
        assert storage.get_section_rows_by_code("rights")
    finally:
        storage.close()

    assert cli.main(["repair-rights"]) == 0
    out = capsys.readouterr().out
    assert "HS 0101210000: Tabla 14" in out

    storage = Storage(db_path)
    try:
        assert storage.get_section_rows_by_code("rights") == {}
        assert storage.get_section_rows_by_code("nomenclature")
        assert storage.get_processed_sections("0101210000") == {"nomenclature"}
        assert storage.get_code("0101210000")["state"] == "pending"
    finally:
        storage.close()
    db_path.unlink(missing_ok=True)
