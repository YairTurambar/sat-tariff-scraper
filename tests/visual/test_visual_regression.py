"""Tolerant visual-regression test for the exported SAT workbook.

This test is intentionally skipped (with an explicit, human-readable reason)
whenever any precondition for a real comparison is missing:

- LibreOffice (`soffice`) and poppler (`pdftoppm`) are not installed, or
- the optional `visual` extra (Pillow/numpy/scikit-image) is not installed, or
- the reference screenshots under `references/` are not present.

When all three preconditions are satisfied, it renders a deterministic
fixture workbook (the same one used by `scripts/compare_excel_visual.py`)
and asserts that each sheet stays within tolerant similarity thresholds of
its reference screenshot. See that script's module docstring for the full
render pipeline and the rationale behind the tolerance thresholds.

Structural correctness (headers, merges, styles, sheet order, number
formats) is verified independently and unconditionally in
`tests/unit/test_exporters.py`; this test only adds a *supplementary* visual
signal and must never be the sole source of truth for correctness.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from compare_excel_visual import (  # noqa: E402
    DEFAULT_MEAN_DIFF_THRESHOLD,
    DEFAULT_SSIM_THRESHOLD,
    SHEET_REFERENCE_FILES,
    compare_workbook_to_references,
    missing_python_deps,
    missing_reference_files,
    missing_render_tools,
)
from sample_workbook import export_sample_workbook  # noqa: E402

REFERENCES_DIR = REPO_ROOT / "references"


def _skip_reason() -> str | None:
    tool_gaps = missing_render_tools()
    if tool_gaps:
        return (
            f"Visual comparison requires {', '.join(tool_gaps)} (LibreOffice + poppler-utils), "
            "which are not installed in this environment."
        )
    dep_gaps = missing_python_deps()
    if dep_gaps:
        return (
            f"Visual comparison requires the optional 'visual' extra (missing: {', '.join(dep_gaps)}). "
            "Install with `pip install -e .[visual]`."
        )
    ref_gaps = missing_reference_files(REFERENCES_DIR)
    if ref_gaps:
        return (
            "Visual comparison requires reference screenshots that are not present in this "
            f"checkout: {', '.join(ref_gaps)}. Add them under references/ (see references/README.md) to "
            "enable this test."
        )
    return None


@pytest.mark.visual
def test_exported_workbook_matches_reference_screenshots(tmp_path):
    reason = _skip_reason()
    if reason:
        pytest.skip(reason)

    workbook_path = export_sample_workbook(tmp_path / "sample_workbook.xlsx")
    results = compare_workbook_to_references(workbook_path, REFERENCES_DIR, tmp_path / "visual-diagnostics")

    assert set(results.keys()) == set(SHEET_REFERENCE_FILES.keys())
    assert all(
        metrics["reference_dimensions"] in {(1853, 91), (1531, 124), (1492, 147), (1460, 137)}
        for metrics in results.values()
    )

    failures = {
        sheet_name: metrics
        for sheet_name, metrics in results.items()
        if metrics["mean_abs_diff"] > DEFAULT_MEAN_DIFF_THRESHOLD or metrics["ssim"] < DEFAULT_SSIM_THRESHOLD
    }
    assert not failures, f"Visual regression detected (see diagnostics in tmp_path/visual-diagnostics): {failures}"
