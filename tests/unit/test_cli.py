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
