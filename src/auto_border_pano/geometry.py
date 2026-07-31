"""Pure image transforms.

Every function here takes and returns PIL Images. Nothing in this module
opens or writes a file, which is what makes it fast to test.
"""

import math
from dataclasses import dataclass

from PIL import Image

SIDE_PADDING = 100
BACKGROUND = "white"


@dataclass(frozen=True)
class AspectRatio:
    """A target output shape.

    Carries the output pixel size alongside the name so the ratio and the
    dimensions it produces cannot drift apart.
    """

    name: str
    width: int
    height: int

    @property
    def value(self) -> float:
        """Width divided by height, for arithmetic."""
        return self.width / self.height


SQUARE = AspectRatio("1:1", 1080, 1080)
PORTRAIT = AspectRatio("4:5", 1080, 1350)
LANDSCAPE = AspectRatio("1.91:1", 1080, 566)

RATIOS: dict[str, AspectRatio] = {r.name: r for r in (SQUARE, PORTRAIT, LANDSCAPE)}
DEFAULT_RATIO = PORTRAIT

MIN_SECTIONS = 2


def section_count(pano_width: int, pano_height: int, ratio: AspectRatio) -> int:
    """How many detail frames to cut from a panorama.

    An exact tile is `pano_height * ratio` wide; the count is how many of
    those fit across the panorama, rounded to nearest.

    The floor of MIN_SECTIONS is deliberate and load-bearing. The detail
    frames exist so a viewer can zoom in on detail; a single detail frame
    would just restate the whole-panorama frame and defeat the purpose. A
    2.4:1 panorama at 1.91:1 is exactly that case -- tiling alone wants one
    frame.

    Half-up rounding, not Python's round(), which is banker's rounding and
    would pick the lower count on exact halves.
    """
    tile = pano_height * ratio.value
    return max(MIN_SECTIONS, math.floor(pano_width / tile + 0.5))


def make_padded_frame(image: Image.Image, ratio: AspectRatio) -> Image.Image:
    """Fit a panorama inside a white canvas of the target ratio, inset by SIDE_PADDING.

    SIDE_PADDING describes the finished frame, in output pixels, on
    whichever axis binds -- not the source image. The panorama is scaled
    (preserving its own aspect ratio) to fit inside a box inset by
    SIDE_PADDING on all four sides, then centered on the full-size white
    canvas.

    For a normal wide panorama the width binds, so the left and right
    margins are exactly SIDE_PADDING and the vertical gap is whatever is
    left over -- usually much larger. That asymmetry is inherent: the
    panorama's aspect ratio does not match the frame's, and frame 1 must
    show the whole panorama uncropped, so the border cannot be made even
    without cropping content away.

    Scaling straight to the fitted size (rather than compositing at source
    scale and downscaling) also avoids building a huge intermediate canvas,
    which matters on multi-hundred-megapixel scans.
    """
    pano_width, pano_height = image.size
    box_width = ratio.width - 2 * SIDE_PADDING
    box_height = ratio.height - 2 * SIDE_PADDING
    scale = min(box_width / pano_width, box_height / pano_height)
    fitted_width = max(1, math.floor(pano_width * scale + 0.5))
    fitted_height = max(1, math.floor(pano_height * scale + 0.5))

    fitted = image.resize((fitted_width, fitted_height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (ratio.width, ratio.height), BACKGROUND)
    canvas.paste(fitted, ((ratio.width - fitted_width) // 2, (ratio.height - fitted_height) // 2))
    return canvas


def section_bounds(width: int, index: int, count: int) -> tuple[int, int]:
    """Return the horizontal crop bounds of one detail frame.

    Uses integer division, so when the width is not divisible by `count`
    the remaining pixels on the right edge are discarded.
    """
    if not 0 <= index < count:
        raise ValueError(f"index must be 0..{count - 1}, got {index}")
    section_width = width // count
    start = index * section_width
    return start, start + section_width


def make_section(image: Image.Image, index: int, count: int, ratio: AspectRatio) -> Image.Image:
    """Crop one detail frame and scale it to exactly fill the target ratio.

    Scales by whichever axis keeps the target fully covered, then
    center-crops the overflow.
    """
    width, height = image.size
    start, end = section_bounds(width, index, count)
    crop = image.crop((start, 0, end, height))
    crop_width, crop_height = crop.size

    scale = max(ratio.width / crop_width, ratio.height / crop_height)
    # Half-up rounding of crop_dim * scale is what actually guarantees the
    # resized image covers the target on both axes. The max(ratio.*, ...)
    # here is belt-and-braces, not load-bearing: it's a floor against any
    # future rounding change, not something exercised by current inputs.
    resized = crop.resize(
        (
            max(ratio.width, math.floor(crop_width * scale + 0.5)),
            max(ratio.height, math.floor(crop_height * scale + 0.5)),
        ),
        Image.Resampling.LANCZOS,
    )

    x_offset = (resized.width - ratio.width) // 2
    y_offset = (resized.height - ratio.height) // 2
    return resized.crop((x_offset, y_offset, x_offset + ratio.width, y_offset + ratio.height))
