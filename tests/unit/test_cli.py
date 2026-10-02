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
