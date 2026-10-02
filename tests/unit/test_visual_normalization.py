"""Unit tests for the non-destructive normalization used by the visual compare.

These tests build their own synthetic images, so they do not need LibreOffice,
poppler or the reference screenshots -- only the optional ``visual`` extra
(Pillow/numpy), without which they are skipped.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

pytest.importorskip("PIL")
pytest.importorskip("numpy")

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from visual_normalization import (  # noqa: E402
    content_bbox,
    flatten_to_rgb,
    normalize_pair,
    trim_uniform_margins,
)


def _sheet_image(
    size=(600, 120),
    margin=20,
    background="white",
    header_color=(68, 114, 196),
    rows=3,
    text="Codigo",
    offset=(0, 0),
    anchors=False,
):
    """Draw a tiny "worksheet": a coloured header band plus bordered rows."""
    image = Image.new("RGB", size, background)
    draw = ImageDraw.Draw(image)
    left = margin + offset[0]
    top = margin + offset[1]
    right = size[0] - margin + offset[0]
    row_height = (size[1] - 2 * margin) // rows
    draw.rectangle([left, top, right, top + row_height], fill=header_color)
    for index in range(rows):
        y0 = top + index * row_height
        draw.rectangle([left, y0, right, y0 + row_height], outline=(0, 0, 0))
        draw.text((left + 6, y0 + 4), f"{text} {index}", fill=(0, 0, 0))
    if anchors:
        # A frame around the whole image so trimming cannot silently absorb a
        # shift of the inner content: the content bbox stays identical in both
        # images and only the alignment search can compensate the offset.
        draw.rectangle([0, 0, size[0] - 1, size[1] - 1], outline=(0, 0, 0))
    return image


def _metrics(image_a, image_b):
    from skimage.metrics import structural_similarity

    normalized_a, normalized_b, report = normalize_pair(image_a, image_b)
    array_a = np.asarray(normalized_a).astype("float64")
    array_b = np.asarray(normalized_b).astype("float64")
    mean_abs_diff = float(np.mean(np.abs(array_a - array_b)) / 255.0)
    ssim = float(
        structural_similarity(array_a, array_b, channel_axis=2, data_range=255.0)
    )
    return mean_abs_diff, ssim, report


def test_flatten_to_rgb_composites_transparency_over_white():
    rgba = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    rgba.putpixel((5, 5), (255, 0, 0, 255))

    flattened = flatten_to_rgb(rgba)

    assert flattened.mode == "RGB"
    assert flattened.getpixel((0, 0)) == (255, 255, 255)
    assert flattened.getpixel((5, 5)) == (255, 0, 0)


def test_trim_removes_only_outer_margins_including_grey_backgrounds():
    image = _sheet_image(background=(240, 240, 240), margin=25)

    bbox = content_bbox(image)
    trimmed = trim_uniform_margins(image)

    assert bbox[0] >= 20 and bbox[1] >= 20
    assert trimmed.width < image.width and trimmed.height < image.height
    # The header band survives the trim: nothing inside the content is cropped.
    assert (np.asarray(trimmed) == np.array([68, 114, 196], dtype=np.uint8)).all(axis=2).any()


def test_normalize_pads_with_white_instead_of_cropping_to_the_shortest():
    short = _sheet_image(size=(600, 90), rows=2)
    tall = _sheet_image(size=(600, 240), rows=6)

    normalized_short, normalized_tall, report = normalize_pair(short, tall)

    assert normalized_short.size == normalized_tall.size
    # The canvas is as tall as the taller image (plus the alignment margin),
    # never cropped down to the shorter one.
    assert normalized_short.height >= max(report.scaled[0][1], report.scaled[1][1])
    # The short image keeps all of its own content and is padded with white.
    short_rows = np.asarray(normalized_short).astype(int).min(axis=(1, 2))
    assert short_rows.max() == 255  # white padding exists
    assert (short_rows < 200).sum() >= report.scaled[0][1] * 0.3  # content survives


def test_normalize_reports_every_dimension_step():
    image_a = _sheet_image(size=(600, 120), margin=20)
    image_b = _sheet_image(size=(900, 180), margin=40)

    _, _, report = normalize_pair(image_a, image_b)

    assert report.original == ((600, 120), (900, 180))
    assert report.trimmed[0][0] < 600 and report.trimmed[1][0] < 900
    assert report.scaled[0][0] == report.scaled[1][0] == report.target_width
    assert report.canvas[0] >= report.target_width


def test_identical_content_with_different_margins_is_near_identical():
    tight = _sheet_image(margin=10)
    loose = _sheet_image(size=(640, 160), margin=30)

    mean_abs_diff, ssim, _ = _metrics(tight, loose)

    assert mean_abs_diff < 0.05
    assert ssim > 0.80


def test_small_translation_is_compensated_by_the_alignment_search():
    straight = _sheet_image(anchors=True)
    shifted = _sheet_image(offset=(4, 3), anchors=True)
    unaligned_a, unaligned_b, _ = normalize_pair(straight, shifted, max_shift=0)
    unaligned_diff = float(
        np.mean(np.abs(np.asarray(unaligned_a).astype(float) - np.asarray(unaligned_b).astype(float))) / 255.0
    )

    mean_abs_diff, ssim, report = _metrics(straight, shifted)

    assert report.alignment_offset != (0, 0)
    assert mean_abs_diff < unaligned_diff
    assert ssim > 0.90


def test_material_color_change_is_detected():
    original = _sheet_image()
    regressed = _sheet_image(header_color=(200, 30, 30))

    mean_abs_diff, ssim, _ = _metrics(original, regressed)

    assert mean_abs_diff > 0.02
    assert ssim < 0.95


def test_material_text_change_is_detected():
    original = _sheet_image(text="Codigo")
    regressed = _sheet_image(text="XXXXXX")

    _, ssim, _ = _metrics(original, regressed)

    assert ssim < 0.98


def test_material_structure_change_is_detected():
    original = _sheet_image(rows=3)
    regressed = _sheet_image(rows=6)

    mean_abs_diff, ssim, _ = _metrics(original, regressed)

    assert mean_abs_diff > 0.01
    assert ssim < 0.95


def test_rgba_reference_matches_its_rgb_equivalent():
    rgb = _sheet_image()
    rgba = rgb.convert("RGBA")

    mean_abs_diff, ssim, _ = _metrics(rgba, rgb)

    assert mean_abs_diff == pytest.approx(0.0, abs=1e-9)
    assert ssim == pytest.approx(1.0, abs=1e-9)
