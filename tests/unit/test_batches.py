"""Offline tests for batch preparation and the manifest format.

No browser, no network and no SAT portal access happen here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sat_tariff.batches import (
    MANIFEST_VERSION,
    BatchError,
    ManifestError,
    build_batch_plans,
    chunk_entries,
    load_batch_entries,
    load_manifest,
    manifest_entries,
    prepare_batches,
    verify_manifest,
)
from sat_tariff.config import AppConfig, ConfigurationError, load_config
from sat_tariff.validation.input_validator import MAX_LINES


def make_config(tmp_path: Path, lines: list[str], **overrides) -> AppConfig:
    master = tmp_path / "HS_codes.txt"
    master.write_text("\n".join(lines) + "\n", encoding="utf-8")
    config = AppConfig(
        input_file=master,
        batch_directory=tmp_path / "batches",
        sqlite_db=tmp_path / "db.sqlite3",
        output_xlsx=tmp_path / "out.xlsx",
        artifacts_dir=tmp_path / "artifacts",
        logs_dir=tmp_path / "logs",
        persistent_profile_dir=tmp_path / "profile",
    )
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def codes(count: int, *, start: int = 0) -> list[str]:
    return [f"{index:010d}" for index in range(start, start + count)]


# 1. empty master file ----------------------------------------------------
def test_empty_master_file_fails(tmp_path):
    config = make_config(tmp_path, ["", "   "])
    with pytest.raises(Exception):
        prepare_batches(config)


# 2 & 3. one batch for 1 and for exactly 500 codes ------------------------
@pytest.mark.parametrize("total", [1, MAX_LINES])
def test_single_batch_for_up_to_the_limit(tmp_path, total):
    config = make_config(tmp_path, codes(total))
    manifest = prepare_batches(config)
    assert len(manifest.batches) == 1
    assert manifest.batches[0].count == total
    assert manifest.total_codes == total


# 4. 501 codes produce 500 + 1 -------------------------------------------
def test_five_hundred_and_one_codes_produce_two_batches(tmp_path):
    config = make_config(tmp_path, codes(MAX_LINES + 1))
    manifest = prepare_batches(config)
    assert [batch.count for batch in manifest.batches] == [MAX_LINES, 1]


# 5. a large master file never produces a batch above the limit -----------
def test_large_master_file_never_exceeds_the_limit(tmp_path):
    total = 7578
    config = make_config(tmp_path, codes(total))
    manifest = prepare_batches(config)
    assert sum(batch.count for batch in manifest.batches) == total
    assert len(manifest.batches) == (total + MAX_LINES - 1) // MAX_LINES
    assert all(batch.count <= MAX_LINES for batch in manifest.batches)


def test_repository_master_file_splits_without_exceeding_the_limit(tmp_path):
    repo_master = Path("HS_codes.txt")
    if not repo_master.exists():  # pragma: no cover - defensive
        pytest.skip("No master file in the repository")
    config = AppConfig(input_file=repo_master, batch_directory=tmp_path / "batches")
    manifest = prepare_batches(config)
    assert manifest.batches
    assert all(batch.count <= MAX_LINES for batch in manifest.batches)
    assert sum(batch.count for batch in manifest.batches) == manifest.total_codes


# 6. leading zeros --------------------------------------------------------
def test_leading_zeros_are_preserved(tmp_path):
    config = make_config(tmp_path, ["0101210000", "0101290000"])
    manifest = prepare_batches(config)
    content = manifest.batch_path(manifest.batches[0]).read_text(encoding="utf-8")
    assert content.splitlines() == ["0101210000", "0101290000"]


# 7. global duplicates ----------------------------------------------------
def test_global_duplicates_are_skipped_keeping_first_occurrence(tmp_path):
    config = make_config(tmp_path, ["0101210000", "0202", "0101210000", "0303"], batch_size=2)
    manifest = prepare_batches(config)
    entries = [entry.normalized_code for entry in manifest_entries(manifest)]
    assert entries == ["0101210000", "0202", "0303"]
    assert manifest.duplicates_skipped == ["0101210000"]
    assert manifest.total_lines == 4
    assert manifest.total_codes == 3


# 8. suspicious policies --------------------------------------------------
def test_suspicious_codes_are_skipped_with_skip_policy(tmp_path):
    config = make_config(tmp_path, ["0101210000", "ABC"], invalid_line_policy="skip")
    manifest = prepare_batches(config)
    assert manifest.total_codes == 1
    assert manifest.suspicious_codes == ["ABC"]


def test_suspicious_codes_are_kept_with_process_policy(tmp_path):
    config = make_config(tmp_path, ["0101210000", "ABC"], invalid_line_policy="process")
    manifest = prepare_batches(config)
    assert manifest.total_codes == 2
    assert manifest.suspicious_codes == ["ABC"]


# 9. batch size bounds ----------------------------------------------------
@pytest.mark.parametrize("size", [0, -1, MAX_LINES + 1])
def test_invalid_batch_size_is_rejected(tmp_path, size):
    config = make_config(tmp_path, codes(3))
    with pytest.raises(BatchError):
        prepare_batches(config, batch_size=size)


def test_env_batch_size_above_the_limit_fails(monkeypatch):
    monkeypatch.setenv("SAT_BATCH_SIZE", str(MAX_LINES + 1))
    with pytest.raises(ConfigurationError):
        load_config()


def test_env_batch_size_defaults_to_the_limit():
    config = load_config()
    assert config.batch_size == MAX_LINES
    assert config.batch_directory == Path("batches")


def test_chunk_entries_rejects_out_of_range_sizes():
    with pytest.raises(BatchError):
        chunk_entries([], 0)


# 10. manifest is valid and versioned -------------------------------------
def test_manifest_is_versioned_and_complete(tmp_path):
    config = make_config(tmp_path, codes(5), batch_size=2)
    manifest = prepare_batches(config)
    payload = json.loads((config.batch_directory / "manifest.json").read_text(encoding="utf-8"))
    assert payload["version"] == MANIFEST_VERSION
    for key in (
        "master_file",
        "master_sha256",
        "created_at",
        "batch_size",
        "total_lines",
        "total_codes",
        "duplicates_skipped",
        "suspicious_codes",
        "batches",
    ):
        assert key in payload
    assert all(set(item) == {"number", "path", "count", "sha256"} for item in payload["batches"])
    reloaded = load_manifest(config.batch_directory)
    assert reloaded.master_sha256 == manifest.master_sha256
    verify_manifest(reloaded)


def test_incompatible_manifest_version_fails(tmp_path):
    config = make_config(tmp_path, codes(3))
    prepare_batches(config)
    path = config.batch_directory / "manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["version"] = MANIFEST_VERSION + 99
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ManifestError):
        load_manifest(config.batch_directory)


def test_missing_or_corrupt_manifest_fails(tmp_path):
    with pytest.raises(ManifestError):
        load_manifest(tmp_path / "batches")
    directory = tmp_path / "batches"
    directory.mkdir()
    (directory / "manifest.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ManifestError):
        load_manifest(directory)


# 11. master file changed after preparing ---------------------------------
def test_modified_master_file_is_detected(tmp_path):
    config = make_config(tmp_path, codes(3))
    prepare_batches(config)
    config.input_file.write_text("0101210000\n", encoding="utf-8")
    manifest = load_manifest(config.batch_directory)
    with pytest.raises(ManifestError) as excinfo:
        verify_manifest(manifest)
    assert "prepare-batches" in str(excinfo.value)


# 12. missing/modified batch files ----------------------------------------
def test_missing_batch_file_fails(tmp_path):
    config = make_config(tmp_path, codes(3), batch_size=2)
    prepare_batches(config)
    manifest = load_manifest(config.batch_directory)
    manifest.batch_path(manifest.batches[1]).unlink()
    with pytest.raises(ManifestError):
        verify_manifest(manifest)


def test_modified_batch_file_fails(tmp_path):
    config = make_config(tmp_path, codes(3), batch_size=2)
    prepare_batches(config)
    manifest = load_manifest(config.batch_directory)
    manifest.batch_path(manifest.batches[0]).write_text("9999999999\n", encoding="utf-8")
    with pytest.raises(ManifestError):
        verify_manifest(manifest)


# 13. deterministic names and portable relative paths ---------------------
def test_batch_names_are_deterministic_and_paths_relative(tmp_path):
    config = make_config(tmp_path, codes(5), batch_size=2)
    first = prepare_batches(config)
    second = prepare_batches(config)
    assert [batch.path for batch in first.batches] == [
        "HS_codes_001.txt",
        "HS_codes_002.txt",
        "HS_codes_003.txt",
    ]
    assert [batch.sha256 for batch in first.batches] == [batch.sha256 for batch in second.batches]
    assert all("/" not in batch.path and "\\" not in batch.path for batch in first.batches)


def test_preparation_only_removes_managed_files(tmp_path):
    config = make_config(tmp_path, codes(5), batch_size=2)
    prepare_batches(config)
    keeper = config.batch_directory / "notas.txt"
    keeper.write_text("no borrar", encoding="utf-8")
    stale = config.batch_directory / "HS_codes_003.txt"
    assert stale.exists()
    config.input_file.write_text("0101210000\n", encoding="utf-8")
    manifest = prepare_batches(config)
    assert keeper.exists()
    assert not stale.exists()
    assert len(manifest.batches) == 1


def test_build_batch_plans_keeps_only_pending_codes(tmp_path):
    config = make_config(tmp_path, codes(5), batch_size=2)
    manifest = prepare_batches(config)
    loaded = load_batch_entries(manifest)
    pending = {"0000000003", "0000000004"}
    plans = build_batch_plans(loaded, pending)
    assert [plan.number for plan in plans] == [2, 3]
    assert [entry.normalized_code for plan in plans for entry in plan.entries] == [
        "0000000003",
        "0000000004",
    ]
    assert all(plan.total_batches == 3 for plan in plans)
