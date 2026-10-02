"""Unit tests for the pure, tool-independent helpers in
``scripts/compare_excel_visual.py``.

These exercise logic that does not require LibreOffice/poppler or the
optional ``visual`` extra to be installed, so they always run as part of the
default (structural) test suite -- unlike ``tests/visual/test_visual_regression.py``,
which is gated on those external tools/dependencies/reference files.
"""

from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from compare_excel_visual import (  # noqa: E402
    SHEET_REFERENCE_FILES,
    _prepare_print_ready_copy,
    missing_reference_files,
    missing_render_tools,
    missing_python_deps,
)
from sample_workbook import export_sample_workbook  # noqa: E402


def test_missing_render_tools_returns_list_of_strings():
    missing = missing_render_tools()
    assert isinstance(missing, list)
    assert all(isinstance(tool, str) for tool in missing)
    assert set(missing) <= {"soffice", "pdftoppm"}


def test_missing_python_deps_returns_list_of_strings():
    missing = missing_python_deps()
    assert isinstance(missing, list)
    assert all(isinstance(dep, str) for dep in missing)
    assert set(missing) <= {"PIL", "numpy", "skimage"}


def test_missing_reference_files_reports_all_four_when_dir_is_empty(tmp_path):
    missing = missing_reference_files(tmp_path)
    assert sorted(missing) == sorted(SHEET_REFERENCE_FILES.values())


def test_missing_reference_files_reports_only_absent_files(tmp_path):
    present = next(iter(SHEET_REFERENCE_FILES.values()))
    (tmp_path / present).write_bytes(b"not-a-real-png")

    missing = missing_reference_files(tmp_path)

    assert present not in missing
    assert set(missing) == set(SHEET_REFERENCE_FILES.values()) - {present}


def test_missing_reference_files_empty_when_all_present(tmp_path):
    for filename in SHEET_REFERENCE_FILES.values():
        (tmp_path / filename).write_bytes(b"not-a-real-png")

    assert missing_reference_files(tmp_path) == []


def test_prepare_print_ready_copy_sets_fit_to_page_for_every_sheet(tmp_path):
    import zipfile

    source = export_sample_workbook(tmp_path / "sample.xlsx")
    destination = tmp_path / "sample.print-ready.xlsx"

    _prepare_print_ready_copy(source, destination)

    # Inspect the written OOXML directly: reloading page_setup with openpyxl
    # after a save/reload round trip is unreliable for this attribute, so we
    # assert on the persisted XML instead of re-parsing with openpyxl.
    with zipfile.ZipFile(destination) as archive:
        sheet_xml_names = [
            name for name in archive.namelist() if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
        ]
        assert sheet_xml_names, "expected at least one worksheet in the print-ready copy"
        for name in sheet_xml_names:
            xml = archive.read(name).decode("utf-8")
            assert 'fitToPage="1"' in xml
            assert 'orientation="landscape"' in xml
