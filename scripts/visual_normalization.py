"""Non-destructive image normalization for the Excel visual comparison.

Why this module exists
----------------------

The first implementation scaled both images to a common width and then cropped
both of them to the *smallest* of the two heights. When a tightly cropped Excel
screenshot (for example 1853x91) was compared with a full LibreOffice page
(1650x1275), that strategy destroyed almost all of the useful content: the
normalized pair ended up being 900x29 pixels, which is far too small to compare
text, borders and header bands in a meaningful way.

The strategy implemented here never discards content:

1. **Flatten to RGB.** RGBA screenshots are composited over an opaque white
   background so transparent pixels never become black.
2. **Trim only uniform outer margins.** The background colour is estimated from
   the image frame (it is white for LibreOffice renders and light grey for an
   Excel screenshot that includes the spreadsheet background), and rows/columns
   whose "ink" is negligible compared to the busiest row/column are removed.
   Interior content is never cropped.
3. **Scale proportionally.** Both images are resized to a shared width with
   LANCZOS resampling, preserving their aspect ratio. The shared width defaults
   to the larger of the two trimmed widths (bounded by ``MAX_TARGET_WIDTH``), so
   the comparison happens at a resolution high enough to resolve glyphs.
4. **Pad onto equally sized white canvases.** Instead of cropping to the
   smallest height, both images are pasted onto white canvases whose size is the
   maximum of both, plus a margin used by the alignment search.
5. **Align with a bounded translation search.** The rendered image is shifted by
   up to ``max_shift`` pixels in each direction and the offset with the smallest
   mean absolute difference wins. This compensates for different outer margins
   without hiding real content changes (the search range is small and the
   content is never resized independently).

Every step reports the dimensions it produced, so the CLI and the tests can log
original, trimmed, scaled and final sizes.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, asdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from PIL.Image import Image as PILImage

#: Images are never upscaled beyond this width during normalization.
MAX_TARGET_WIDTH = 2400
#: Minimum shared width, so very small crops are still comparable.
MIN_TARGET_WIDTH = 600
#: Per-channel tolerance (0-255) used when deciding whether a pixel differs
#: from the estimated background colour.
BACKGROUND_TOLERANCE = 16
#: A row/column is considered empty margin when its ink is below this fraction
#: of the busiest row/column.
MARGIN_INK_RATIO = 0.05
#: Maximum translation (in normalized pixels) explored while aligning.
DEFAULT_MAX_SHIFT = 12


@dataclass
class NormalizationReport:
    """Dimensions produced by every normalization step."""

    original: tuple[tuple[int, int], tuple[int, int]]
    trimmed: tuple[tuple[int, int], tuple[int, int]]
    scaled: tuple[tuple[int, int], tuple[int, int]]
    canvas: tuple[int, int]
    target_width: int
    alignment_offset: tuple[int, int] = field(default=(0, 0))

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def flatten_to_rgb(image: "PILImage") -> "PILImage":
    """Return *image* as RGB, compositing any alpha channel over white."""
    from PIL import Image

    if image.mode == "RGB":
        return image.copy()
    rgba = image.convert("RGBA")
    background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    return Image.alpha_composite(background, rgba).convert("RGB")


def estimate_background_color(array) -> tuple[int, int, int]:
    """Estimate the background colour from the one-pixel frame of *array*."""
    import numpy as np

    frame = np.concatenate([array[0], array[-1], array[:, 0], array[:, -1]])
    most_common = Counter(map(tuple, frame.tolist())).most_common(1)[0][0]
    return tuple(int(channel) for channel in most_common)


def content_bbox(
    image: "PILImage",
    tolerance: int = BACKGROUND_TOLERANCE,
    ink_ratio: float = MARGIN_INK_RATIO,
) -> tuple[int, int, int, int]:
    """Return the ``(left, upper, right, lower)`` box of the useful content.

    Only *outer* rows/columns whose ink is negligible compared to the busiest
    row/column are excluded, so faint but uniform spreadsheet backgrounds (and
    the grid lines drawn on them) are trimmed while real content is kept.
    """
    import numpy as np

    array = np.asarray(flatten_to_rgb(image)).astype(np.int16)
    background = np.array(estimate_background_color(array), dtype=np.int16)
    mask = np.abs(array - background).max(axis=2) > tolerance

    def bounds(ink) -> tuple[int, int] | None:
        if ink.max() == 0:
            return None
        threshold = max(2.0, ink_ratio * float(ink.max()))
        indices = np.nonzero(ink >= threshold)[0]
        if indices.size == 0:
            return None
        return int(indices[0]), int(indices[-1])

    rows = bounds(mask.sum(axis=1))
    columns = bounds(mask.sum(axis=0))
    if rows is None or columns is None:
        return (0, 0, image.width, image.height)
    return (columns[0], rows[0], columns[1] + 1, rows[1] + 1)


def trim_uniform_margins(
    image: "PILImage",
    tolerance: int = BACKGROUND_TOLERANCE,
    ink_ratio: float = MARGIN_INK_RATIO,
) -> "PILImage":
    """Crop the uniform outer margins of *image* (never its interior)."""
    rgb_image = flatten_to_rgb(image)
    return rgb_image.crop(content_bbox(rgb_image, tolerance, ink_ratio))


def scale_to_width(image: "PILImage", width: int) -> "PILImage":
    """Resize *image* to *width* preserving its aspect ratio."""
    from PIL import Image

    if image.width == width:
        return image
    height = max(1, round(image.height * width / image.width))
    return image.resize((width, height), Image.LANCZOS)


def _paste_on_canvas(image: "PILImage", size: tuple[int, int], offset: tuple[int, int]):
    from PIL import Image

    canvas = Image.new("RGB", size, (255, 255, 255))
    canvas.paste(image, offset)
    return canvas


def _mean_abs_diff(array_a, array_b) -> float:
    import numpy as np

    return float(np.mean(np.abs(array_a - array_b)) / 255.0)


def normalize_pair(
    image_a: "PILImage",
    image_b: "PILImage",
    target_width: int | None = None,
    max_shift: int = DEFAULT_MAX_SHIFT,
) -> tuple["PILImage", "PILImage", NormalizationReport]:
    """Normalize two sheet images without discarding any of their content.

    Returns ``(normalized_a, normalized_b, report)``. Both normalized images
    have exactly the same size and are padded with white instead of being
    cropped to the smaller one.
    """
    import numpy as np

    original = (image_a.size, image_b.size)
    trimmed_a = trim_uniform_margins(image_a)
    trimmed_b = trim_uniform_margins(image_b)
    trimmed = (trimmed_a.size, trimmed_b.size)

    if target_width is None:
        target_width = max(trimmed_a.width, trimmed_b.width)
    target_width = int(min(MAX_TARGET_WIDTH, max(MIN_TARGET_WIDTH, target_width)))

    scaled_a = scale_to_width(trimmed_a, target_width)
    scaled_b = scale_to_width(trimmed_b, target_width)
    scaled = (scaled_a.size, scaled_b.size)

    max_shift = max(0, int(max_shift))
    canvas_size = (
        target_width + 2 * max_shift,
        max(scaled_a.height, scaled_b.height) + 2 * max_shift,
    )

    canvas_a = _paste_on_canvas(scaled_a, canvas_size, (max_shift, max_shift))
    array_a = np.asarray(canvas_a).astype(np.float64)

    best_offset = (0, 0)
    best_canvas = _paste_on_canvas(scaled_b, canvas_size, (max_shift, max_shift))
    best_score = _mean_abs_diff(array_a, np.asarray(best_canvas).astype(np.float64))

    def evaluate(offsets) -> None:
        nonlocal best_score, best_offset, best_canvas
        for dx, dy in offsets:
            if (dx, dy) == best_offset:
                continue
            candidate = _paste_on_canvas(scaled_b, canvas_size, (max_shift + dx, max_shift + dy))
            score = _mean_abs_diff(array_a, np.asarray(candidate).astype(np.float64))
            if score < best_score:
                best_score, best_offset, best_canvas = score, (dx, dy), candidate

    if max_shift:
        # Coarse-to-fine search: a strided sweep over the whole range, then a
        # single-pixel refinement around the best coarse offset. This keeps the
        # cost low while still finding one-pixel misalignments, which matter a
        # lot for the strict renderer-baseline thresholds.
        step = max(1, max_shift // 6)
        evaluate(
            (dx, dy)
            for dx in range(-max_shift, max_shift + 1, step)
            for dy in range(-max_shift, max_shift + 1, step)
        )
        coarse_dx, coarse_dy = best_offset
        evaluate(
            (dx, dy)
            for dx in range(coarse_dx - step + 1, coarse_dx + step)
            for dy in range(coarse_dy - step + 1, coarse_dy + step)
            if abs(dx) <= max_shift and abs(dy) <= max_shift
        )

    report = NormalizationReport(
        original=original,
        trimmed=trimmed,
        scaled=scaled,
        canvas=canvas_size,
        target_width=target_width,
        alignment_offset=best_offset,
    )
    return canvas_a, best_canvas, report
