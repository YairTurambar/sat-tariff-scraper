"""Reproducible rendering and two-level visual comparison for the SAT workbook.

Render pipeline (documented so it can be reproduced outside this environment):

1. Export a deterministic fixture workbook with the real exporter
   (``scripts/sample_workbook.py``).
2. Convert the workbook to PDF with LibreOffice headless:
   ``soffice --headless --convert-to pdf --outdir <dir> <workbook.xlsx>``
3. Rasterize each PDF page to PNG with poppler's ``pdftoppm``:
   ``pdftoppm -png -r <dpi> <file.pdf> <prefix>``
   LibreOffice emits one page per worksheet in workbook order when each sheet
   fits on a single page (this module forces that by setting a tight
   `fit-to-page` print setup on a throwaway copy of the workbook before
   conversion), so PDF page *N* corresponds to ``SHEET_ORDER[N - 1]``.
4. Normalize the rendered sheet and its counterpart without destroying content
   (see ``scripts/visual_normalization.py``) and compute mean absolute pixel
   difference and SSIM.

Two explicit comparison modes exist, because they answer different questions:

``--mode design``
    Compares against the **human/design references** in ``references/`` (real
    Excel screenshots). This is a *cross-engine* comparison: LibreOffice is not
    Excel, so the thresholds are deliberately tolerant and no pixel equivalence
    is claimed. Sheet structure, headers and styles are additionally asserted
    with ``openpyxl`` (``validate_workbook_against_spec``), which is the exact
    part of the specification that a tolerant pixel metric cannot prove.

``--mode baseline``
    Compares against a **renderer baseline**: PNGs previously produced by this
    very pipeline from an approved workbook and stored under
    ``tests/visual/baselines/libreoffice/`` together with a JSON manifest
    (LibreOffice version, platform, DPI, dimensions, SHA-256 hashes, creation
    date and the command used). Because both sides come from the same engine
    and configuration, the thresholds are strict; only anti-aliasing noise is
    tolerated. The baseline is never regenerated implicitly: use
    ``python scripts/update_visual_baseline.py --confirm``.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile

from openpyxl import load_workbook

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from sample_workbook import export_sample_workbook  # noqa: E402
from visual_normalization import normalize_pair  # noqa: E402

SHEET_ORDER = ["Derechos e impuestos", "Nomenclatura", "Restricciones", "Cuotas"]
SHEET_REFERENCE_FILES = {
    "Derechos e impuestos": "derechos_e_impuestos.png",
    "Nomenclatura": "nomenclatura.png",
    "Restricciones": "restricciones.png",
    "Cuotas": "cuotas.png",
}
REAL_REFERENCE_FILE_ALIASES = {
    "derechos_e_impuestos.png": "Derechos e impuestos.png",
    "nomenclatura.png": "Nomenclatura.png",
    "restricciones.png": "Restricciones.png",
    "cuotas.png": "Cuotas.png",
}

REQUIRED_TOOLS = ("soffice", "pdftoppm")

#: Rasterization resolution. 200 dpi keeps a full letter page under ~2200x1700
#: pixels while rendering the (down-scaled, fit-to-page) sheet content at a
#: resolution comparable to the Excel screenshots.
RENDER_DPI = 200

BASELINE_DIR = REPO_ROOT / "tests" / "visual" / "baselines" / "libreoffice"
BASELINE_MANIFEST_NAME = "manifest.json"
BASELINE_UPDATE_COMMAND = "python scripts/update_visual_baseline.py --confirm"
#: White margin kept around the stored baseline crop (see write_baseline).
BASELINE_MARGIN = 10

# ---------------------------------------------------------------------------
# Thresholds
#
# Design mode (Excel screenshot vs LibreOffice render) is cross-engine: fonts,
# hinting, anti-aliasing and auto row heights differ, so SSIM never approaches
# 1.0 even for a correct sheet. The values below were calibrated against the
# four real screenshots after the normalization rewrite; see
# references/README.md for the measured per-sheet numbers.
DESIGN_MEAN_DIFF_THRESHOLD = 0.18
DESIGN_SSIM_THRESHOLD = 0.35
# Baseline mode compares two outputs of the *same* engine and configuration, so
# only anti-aliasing noise is expected; anything else must fail.
BASELINE_MEAN_DIFF_THRESHOLD = 0.01
BASELINE_SSIM_THRESHOLD = 0.98

MODES = ("design", "baseline")


class VisualToolingUnavailable(RuntimeError):
    """Raised when LibreOffice/poppler or the optional Python deps are missing."""


class BaselineUnavailable(RuntimeError):
    """Raised when the renderer baseline is missing or incompatible."""


def missing_render_tools() -> list[str]:
    return [tool for tool in REQUIRED_TOOLS if shutil.which(tool) is None]


def missing_python_deps() -> list[str]:
    missing = []
    for module_name in ("PIL", "numpy", "skimage"):
        try:
            __import__(module_name)
        except ImportError:
            missing.append(module_name)
    return missing


def missing_reference_files(references_dir: Path) -> list[str]:
    return [
        filename
        for filename in SHEET_REFERENCE_FILES.values()
        if resolve_reference_path(references_dir, filename) is None
    ]


def resolve_reference_path(references_dir: Path, canonical_filename: str) -> Path | None:
    """Return the canonical reference or the real screenshot filename."""
    candidates = (canonical_filename, REAL_REFERENCE_FILE_ALIASES.get(canonical_filename, ""))
    for filename in candidates:
        if filename and (references_dir / filename).is_file():
            return references_dir / filename
    return None


def _page_sort_key(path: Path) -> int:
    """Sort rendered ``page-N.png`` files numerically (not lexicographically).

    Lexicographic sorting would put ``page-10.png`` before ``page-2.png``; we
    extract the numeric page suffix so ordering stays correct regardless of
    how many sheets/pages are rendered.
    """
    match = re.search(r"-(\d+)\.png$", path.name)
    return int(match.group(1)) if match else 0


def _prepare_print_ready_copy(xlsx_path: Path, destination: Path) -> None:
    """Copy *xlsx_path* and force one-page-per-sheet so PDF pages align with sheets."""
    workbook = load_workbook(xlsx_path)
    for sheet_name in workbook.sheetnames:
        worksheet = workbook[sheet_name]
        worksheet.page_setup.fitToPage = True
        worksheet.page_setup.fitToWidth = 1
        worksheet.page_setup.fitToHeight = 1
        worksheet.sheet_properties.pageSetUpPr.fitToPage = True
        worksheet.page_setup.orientation = "landscape"
    workbook.save(destination)


def render_workbook_to_images(xlsx_path: Path, out_dir: Path, dpi: int = RENDER_DPI) -> dict[str, Path]:
    """Render each sheet of *xlsx_path* to a PNG inside *out_dir*.

    Returns a mapping of sheet name -> PNG path. Raises
    :class:`VisualToolingUnavailable` if LibreOffice/poppler are not installed.
    """
    missing = missing_render_tools()
    if missing:
        raise VisualToolingUnavailable(f"Missing required tools: {missing}")

    out_dir.mkdir(parents=True, exist_ok=True)
    print_ready_path = out_dir / f"{xlsx_path.stem}.print-ready.xlsx"
    _prepare_print_ready_copy(xlsx_path, print_ready_path)

    subprocess.run(
        [
            "soffice",
            "--headless",
            "--norestore",
            "--convert-to",
            "pdf",
            "--outdir",
            str(out_dir),
            str(print_ready_path),
        ],
        check=True,
        capture_output=True,
    )
    pdf_path = out_dir / f"{print_ready_path.stem}.pdf"
    if not pdf_path.is_file():
        raise VisualToolingUnavailable(f"LibreOffice did not produce the expected PDF at {pdf_path}")

    raster_prefix = out_dir / "page"
    subprocess.run(
        ["pdftoppm", "-png", "-r", str(dpi), str(pdf_path), str(raster_prefix)],
        check=True,
        capture_output=True,
    )

    rendered_pages = sorted(out_dir.glob("page-*.png"), key=_page_sort_key)
    if len(rendered_pages) != len(SHEET_ORDER):
        raise VisualToolingUnavailable(
            f"Expected {len(SHEET_ORDER)} rendered pages (one per sheet) but found {len(rendered_pages)}: "
            f"{[path.name for path in rendered_pages]}. Each worksheet must fit on a single PDF page."
        )
    return {sheet_name: page_path for sheet_name, page_path in zip(SHEET_ORDER, rendered_pages)}


def compare_images(
    reference_path: Path,
    rendered_path: Path,
    diff_output_path: Path | None = None,
    normalized_output_prefix: Path | None = None,
) -> dict[str, object]:
    """Compute similarity metrics between two sheet images.

    The pair is normalized with :func:`visual_normalization.normalize_pair`
    (trim uniform margins, proportional scaling, white padding and a bounded
    alignment search) so no content is cropped away before measuring.
    """
    import numpy as np
    from PIL import Image
    from skimage.metrics import structural_similarity

    with Image.open(reference_path) as reference_image, Image.open(rendered_path) as rendered_image:
        normalized_reference, normalized_rendered, report = normalize_pair(
            reference_image, rendered_image
        )

    reference_array = np.asarray(normalized_reference).astype("float64")
    rendered_array = np.asarray(normalized_rendered).astype("float64")

    mean_abs_diff = float(np.mean(np.abs(reference_array - rendered_array)) / 255.0)
    similarity, diff_image = structural_similarity(
        reference_array,
        rendered_array,
        channel_axis=2,
        full=True,
        data_range=255.0,
    )

    if normalized_output_prefix is not None:
        normalized_output_prefix.parent.mkdir(parents=True, exist_ok=True)
        normalized_reference.save(normalized_output_prefix.with_name(f"{normalized_output_prefix.name}.expected.png"))
        normalized_rendered.save(normalized_output_prefix.with_name(f"{normalized_output_prefix.name}.actual.png"))

    if diff_output_path is not None:
        diff_output_path.parent.mkdir(parents=True, exist_ok=True)
        diff_normalized = (1 - diff_image).clip(0, 1)
        diff_visual = (diff_normalized.mean(axis=2) * 255).astype("uint8")
        Image.fromarray(diff_visual).save(diff_output_path)

    return {
        "mean_abs_diff": mean_abs_diff,
        "ssim": float(similarity),
        "reference_dimensions": report.original[0],
        "rendered_dimensions": report.original[1],
        "trimmed_dimensions": report.trimmed,
        "scaled_dimensions": report.scaled,
        "normalized_dimensions": report.canvas,
        "alignment_offset": report.alignment_offset,
    }


def validate_workbook_against_spec(xlsx_path: Path) -> None:
    """Assert the structural part of the spec with ``openpyxl``.

    Pixel metrics across two rendering engines cannot prove header names,
    column order or styles; this complementary check does, and it is what the
    design-reference mode relies on for exact text/structure correctness.
    """
    from sat_tariff.exporters.layouts import RIGHTS_BASE_HEADERS, RIGHTS_TRAILING_HEADERS
    from sat_tariff.exporters.styles import HEADER_FILL, HEADER_FONT
    from sat_tariff.validation.output_validator import validate_workbook_structure

    validate_workbook_structure(xlsx_path)
    workbook = load_workbook(xlsx_path)
    if workbook.sheetnames != SHEET_ORDER:
        raise ValueError(f"Unexpected sheet order: {workbook.sheetnames}")

    rights = workbook["Derechos e impuestos"]
    headers = [cell.value for cell in rights[1]]
    if headers[: len(RIGHTS_BASE_HEADERS)] != RIGHTS_BASE_HEADERS:
        raise ValueError(f"Unexpected leading rights headers: {headers[: len(RIGHTS_BASE_HEADERS)]}")
    if headers[-len(RIGHTS_TRAILING_HEADERS) :] != RIGHTS_TRAILING_HEADERS:
        raise ValueError(f"Unexpected trailing rights headers: {headers[-len(RIGHTS_TRAILING_HEADERS):]}")
    if rights[2][0].value is None:
        raise ValueError("The rights sheet has a header row but no data rows")

    expected_fill = HEADER_FILL.fgColor.rgb
    expected_color = HEADER_FONT.color.rgb
    for cell in rights[1]:
        if cell.fill.fgColor.rgb != expected_fill:
            raise ValueError(f"Header fill mismatch in {cell.coordinate}: {cell.fill.fgColor.rgb}")
        if cell.font.color is None or cell.font.color.rgb != expected_color or not cell.font.bold:
            raise ValueError(f"Header font mismatch in {cell.coordinate}")


def compare_workbook_to_references(
    xlsx_path: Path, references_dir: Path, diagnostics_dir: Path
) -> dict[str, dict[str, object]]:
    """Design mode: render *xlsx_path* and compare it with the Excel screenshots."""
    rendered_pages = render_workbook_to_images(xlsx_path, diagnostics_dir / "rendered")
    results: dict[str, dict[str, object]] = {}
    for sheet_name, rendered_path in rendered_pages.items():
        canonical_filename = SHEET_REFERENCE_FILES[sheet_name]
        reference_path = resolve_reference_path(references_dir, canonical_filename)
        if reference_path is None:
            raise FileNotFoundError(f"Reference screenshot not found for {sheet_name}: {canonical_filename}")
        stem = Path(canonical_filename).stem
        results[sheet_name] = compare_images(
            reference_path,
            rendered_path,
            diagnostics_dir / "diffs" / f"design-{stem}.png",
            diagnostics_dir / "normalized" / f"design-{stem}",
        )
    return results


# ---------------------------------------------------------------------------
# Renderer baseline (mode B)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _tool_version(command: list[str]) -> str:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as error:  # pragma: no cover - depends on the environment
        return f"unavailable ({error})"
    output = (completed.stdout or completed.stderr or "").strip().splitlines()
    return output[0] if output else "unknown"


def load_baseline_manifest(baseline_dir: Path = BASELINE_DIR) -> dict[str, object]:
    """Load and sanity-check the baseline manifest.

    Raises :class:`BaselineUnavailable` with an actionable message when the
    baseline is missing, incomplete, corrupted or was produced with a different
    render configuration.
    """
    manifest_path = baseline_dir / BASELINE_MANIFEST_NAME
    if not manifest_path.is_file():
        raise BaselineUnavailable(
            f"No renderer baseline manifest at {manifest_path}. Generate one with: {BASELINE_UPDATE_COMMAND}"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise BaselineUnavailable(f"Corrupted baseline manifest {manifest_path}: {error}") from error

    sheets = manifest.get("sheets", {})
    missing = [sheet for sheet in SHEET_ORDER if sheet not in sheets]
    if missing:
        raise BaselineUnavailable(
            f"Baseline manifest {manifest_path} does not cover {missing}. Regenerate it with: {BASELINE_UPDATE_COMMAND}"
        )
    if manifest.get("dpi") != RENDER_DPI:
        raise BaselineUnavailable(
            f"Baseline was generated at {manifest.get('dpi')} dpi but this pipeline renders at {RENDER_DPI} dpi. "
            f"Regenerate it with: {BASELINE_UPDATE_COMMAND}"
        )
    for sheet_name, entry in sheets.items():
        image_path = baseline_dir / entry["file"]
        if not image_path.is_file():
            raise BaselineUnavailable(
                f"Baseline image for {sheet_name} is missing: {image_path}. Regenerate it with: {BASELINE_UPDATE_COMMAND}"
            )
        actual_hash = sha256_of(image_path)
        if actual_hash != entry.get("sha256"):
            raise BaselineUnavailable(
                f"Baseline image {image_path.name} does not match its manifest hash "
                f"({actual_hash} != {entry.get('sha256')}). Regenerate it with: {BASELINE_UPDATE_COMMAND}"
            )
    return manifest


def baseline_filename(sheet_name: str) -> str:
    return SHEET_REFERENCE_FILES[sheet_name]


def write_baseline(xlsx_path: Path, baseline_dir: Path, work_dir: Path) -> dict[str, object]:
    """Render *xlsx_path* and store the per-sheet baseline images + manifest."""
    from PIL import Image

    from visual_normalization import trim_uniform_margins

    rendered_pages = render_workbook_to_images(xlsx_path, work_dir / "rendered")
    baseline_dir.mkdir(parents=True, exist_ok=True)
    sheets: dict[str, object] = {}
    for sheet_name, rendered_path in rendered_pages.items():
        destination = baseline_dir / baseline_filename(sheet_name)
        with Image.open(rendered_path) as rendered_image:
            # Store the content bounding box instead of the whole letter page:
            # identical information for the comparison, a fraction of the size.
            # A white margin is kept around it so that re-trimming the stored
            # baseline reproduces exactly the same crop (without it, the outer
            # cell border would be mistaken for the background frame).
            content = trim_uniform_margins(rendered_image)
            framed = Image.new(
                "RGB",
                (content.width + 2 * BASELINE_MARGIN, content.height + 2 * BASELINE_MARGIN),
                (255, 255, 255),
            )
            framed.paste(content, (BASELINE_MARGIN, BASELINE_MARGIN))
            framed.save(destination)
        with Image.open(destination) as stored:
            dimensions = list(stored.size)
        sheets[sheet_name] = {
            "file": destination.name,
            "dimensions": dimensions,
            "sha256": sha256_of(destination),
        }

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "command": BASELINE_UPDATE_COMMAND,
        "libreoffice_version": _tool_version(["soffice", "--version"]),
        "pdftoppm_version": _tool_version(["pdftoppm", "-v"]),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "dpi": RENDER_DPI,
        "render_pipeline": "soffice --headless --convert-to pdf -> pdftoppm -png -r {dpi} -> trim uniform margins".format(dpi=RENDER_DPI),
        "sheets": sheets,
    }
    (baseline_dir / BASELINE_MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def compare_workbook_to_baseline(
    xlsx_path: Path, baseline_dir: Path, diagnostics_dir: Path
) -> dict[str, dict[str, object]]:
    """Baseline mode: compare a fresh render with the approved LibreOffice baseline."""
    manifest = load_baseline_manifest(baseline_dir)
    rendered_pages = render_workbook_to_images(xlsx_path, diagnostics_dir / "rendered")
    results: dict[str, dict[str, object]] = {}
    for sheet_name, rendered_path in rendered_pages.items():
        entry = manifest["sheets"][sheet_name]
        baseline_path = baseline_dir / entry["file"]
        stem = Path(entry["file"]).stem
        metrics = compare_images(
            baseline_path,
            rendered_path,
            diagnostics_dir / "diffs" / f"baseline-{stem}.png",
            diagnostics_dir / "normalized" / f"baseline-{stem}",
        )
        metrics["baseline_dimensions"] = tuple(entry["dimensions"])
        results[sheet_name] = metrics
    return results


def thresholds_for_mode(mode: str) -> tuple[float, float]:
    if mode == "baseline":
        return BASELINE_MEAN_DIFF_THRESHOLD, BASELINE_SSIM_THRESHOLD
    return DESIGN_MEAN_DIFF_THRESHOLD, DESIGN_SSIM_THRESHOLD


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--mode",
        choices=MODES,
        default="design",
        help=(
            "design: tolerant comparison against the Excel screenshots in references/ "
            "(human design reference). baseline: strict comparison against the approved "
            "LibreOffice baseline under tests/visual/baselines/libreoffice/."
        ),
    )
    parser.add_argument("--workbook", type=Path, default=None, help="Existing workbook to compare. Default: generate the fixture sample workbook.")
    parser.add_argument("--references-dir", type=Path, default=REPO_ROOT / "references")
    parser.add_argument("--baseline-dir", type=Path, default=BASELINE_DIR)
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "artifacts" / "visual")
    parser.add_argument("--mean-diff-threshold", type=float, default=None)
    parser.add_argument("--ssim-threshold", type=float, default=None)
    args = parser.parse_args(argv)

    default_mean, default_ssim = thresholds_for_mode(args.mode)
    mean_threshold = default_mean if args.mean_diff_threshold is None else args.mean_diff_threshold
    ssim_threshold = default_ssim if args.ssim_threshold is None else args.ssim_threshold

    tool_gaps = missing_render_tools()
    if tool_gaps:
        print(f"SKIP: missing rendering tools {', '.join(tool_gaps)}. Install LibreOffice and poppler-utils.")
        return 2
    dep_gaps = missing_python_deps()
    if dep_gaps:
        print(f"SKIP: missing optional Python dependencies {', '.join(dep_gaps)}. Install with `pip install -e .[visual]`.")
        return 2
    if args.mode == "design":
        ref_gaps = missing_reference_files(args.references_dir)
        if ref_gaps:
            print(f"SKIP: missing reference screenshots under {args.references_dir}: {', '.join(ref_gaps)}")
            return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)

    def run(workbook_path: Path) -> dict[str, dict[str, object]]:
        if args.mode == "design":
            validate_workbook_against_spec(workbook_path)
            return compare_workbook_to_references(workbook_path, args.references_dir, args.output_dir)
        return compare_workbook_to_baseline(workbook_path, args.baseline_dir, args.output_dir)

    try:
        if args.workbook is None:
            with tempfile.TemporaryDirectory() as tmp:
                results = run(export_sample_workbook(Path(tmp) / "sample_workbook.xlsx"))
        else:
            results = run(args.workbook)
    except BaselineUnavailable as error:
        print(f"ERROR: {error}")
        return 3

    exit_code = 0
    print(f"mode={args.mode} mean_diff<={mean_threshold} ssim>={ssim_threshold} dpi={RENDER_DPI}")
    print(f"{'Sheet':<24}{'mean_abs_diff':>15}{'ssim':>9}  expected    actual      normalized   shift   status")
    for sheet_name, metrics in results.items():
        passed = metrics["mean_abs_diff"] <= mean_threshold and metrics["ssim"] >= ssim_threshold
        if not passed:
            exit_code = 1
        print(
            f"{sheet_name:<24}{metrics['mean_abs_diff']:>15.4f}{metrics['ssim']:>9.4f}"
            f"  {metrics['reference_dimensions']!s:<11} {metrics['rendered_dimensions']!s:<11}"
            f" {metrics['normalized_dimensions']!s:<12} {metrics['alignment_offset']!s:<8}"
            f" {'OK' if passed else 'FAIL'}"
        )
    print(f"Diagnostics (normalized pairs and diff images) written under {args.output_dir}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
