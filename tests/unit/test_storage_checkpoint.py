from pathlib import Path
import uuid

from sat_tariff.checkpoint import build_resume_point, next_section_for_state
from sat_tariff.models import ProcessingState, RightsTaxesRow
from sat_tariff.storage import Storage


def make_db_path() -> Path:
    path = Path("data") / f"test-storage-{uuid.uuid4().hex}.sqlite3"
    if path.exists():
        path.unlink()
    return path


def test_storage_create_commit_and_resume_progress():
    db_path = make_db_path()
    storage = Storage(db_path)
    try:
        storage.upsert_code("9999000001", "9999000001")
        storage.save_section_rows("9999000001", "rights", [RightsTaxesRow("TRATAMIENTO GENERAL", "DAI", "desc", "AD1", "5%", "CQ1")], section_status="ok")
        storage.update_state("9999000001", ProcessingState.rights_completed)
    finally:
        storage.close()

    reopened = Storage(db_path)
    try:
        code_row = reopened.get_code("9999000001")
        assert code_row is not None
        assert code_row["state"] == ProcessingState.rights_completed.value
        resume_point = build_resume_point("9999000001", code_row["state"])
        assert resume_point.next_section == "nomenclature"
        export_payload = reopened.load_all_for_export()
        assert export_payload[0]["rights"]["rows"][0]["agreement_name"] == "TRATAMIENTO GENERAL"
    finally:
        reopened.close()
        db_path.unlink(missing_ok=True)


def test_transaction_rolls_back_on_error():
    db_path = make_db_path()
    storage = Storage(db_path)
    try:
        storage.upsert_code("9999000002", "9999000002")
        try:
            with storage.transaction() as conn:
                conn.execute("UPDATE hs_codes SET state = ? WHERE code = ?", (ProcessingState.in_progress.value, "9999000002"))
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        assert storage.get_code("9999000002")["state"] == ProcessingState.pending.value
    finally:
        storage.close()
        db_path.unlink(missing_ok=True)


def test_completed_and_permanent_error_have_no_next_section():
    assert next_section_for_state(ProcessingState.completed) is None
    assert next_section_for_state(ProcessingState.permanent_error) is None


def test_resume_point_uses_processed_sections_for_retryable_error():
    db_path = make_db_path()
    storage = Storage(db_path)
    try:
        storage.upsert_code("9999000003", "9999000003", ProcessingState.retryable_error)
        storage.save_section_rows(
            "9999000003",
            "rights",
            [RightsTaxesRow("TRATAMIENTO GENERAL", "DAI", "desc", "AD1", "5%", "CQ1")],
            section_status="ok",
        )
        resume_point = build_resume_point(
            "9999000003",
            ProcessingState.retryable_error.value,
            storage.get_processed_sections("9999000003"),
        )
        assert resume_point.next_section == "nomenclature"
    finally:
        storage.close()
        db_path.unlink(missing_ok=True)
