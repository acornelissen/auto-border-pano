"""Pure image transforms.

Every function here takes and returns PIL Images. Nothing in this module
opens or writes a file, which is what makes it fast to test.
"""

import math
from dataclasses import dataclass

from PIL import Image

SIDE_PADDING = 100
VERTICAL_PADDING = 10
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


def padded_frame_size(
    pano_width: int, pano_height: int, ratio: AspectRatio
) -> tuple[int, int]:
    """Canvas size for the whole-panorama frame at a given ratio.

    Sized from the width so the panorama keeps SIDE_PADDING left and right.
    If the ratio would then make the canvas too short to hold the panorama
    with its minimum vertical padding, size from the height instead. Either
    way the ratio is exact.
    """
    width = pano_width + 2 * SIDE_PADDING
    height = math.floor(width / ratio.value + 0.5)

    minimum_height = pano_height + 2 * VERTICAL_PADDING
    if height < minimum_height:
        height = minimum_height
        width = math.floor(height * ratio.value + 0.5)
    return width, height


def make_padded_frame(image: Image.Image, ratio: AspectRatio) -> Image.Image:
    """Center a panorama on a white canvas of the target ratio.

    The panorama is centered, so at a tall ratio most of the frame is white
    border. That is the intended aesthetic, not a bug.
    """
    pano_width, pano_height = image.size
    width, height = padded_frame_size(pano_width, pano_height, ratio)
    canvas = Image.new("RGB", (width, height), BACKGROUND)
    canvas.paste(image, ((width - pano_width) // 2, (height - pano_height) // 2))
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


def make_section(
    image: Image.Image, index: int, count: int, ratio: AspectRatio
) -> Image.Image:
    """Crop one detail frame and scale it to exactly fill the target ratio.

    Scales by whichever axis keeps the target fully covered, then
    center-crops the overflow.
    """
    width, height = image.size
    start, end = section_bounds(width, index, count)
    crop = image.crop((start, 0, end, height))
    crop_width, crop_height = crop.size

    scale = max(ratio.width / crop_width, ratio.height / crop_height)
    resized = crop.resize(
        (
            max(ratio.width, math.floor(crop_width * scale + 0.5)),
            max(ratio.height, math.floor(crop_height * scale + 0.5)),
        ),
        Image.Resampling.LANCZOS,
    )

    x_offset = (resized.width - ratio.width) // 2
    y_offset = (resized.height - ratio.height) // 2
    return resized.crop(
        (x_offset, y_offset, x_offset + ratio.width, y_offset + ratio.height)
    )
