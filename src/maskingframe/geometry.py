"""Pure image transforms.

Every function here takes and returns PIL Images. Nothing in this module
opens or writes a file, which is what makes it fast to test.
"""

import math
import re
from dataclasses import dataclass

from PIL import Image


@dataclass(frozen=True)
class AspectRatio:
    """A target output shape.

    Carries the output pixel size alongside the name so the ratio and the
    dimensions it produces cannot drift apart.
    """

    name: str
    width: int
    height: int
    label: str = ""

    def __post_init__(self) -> None:
        if not self.label:
            object.__setattr__(self, "label", self.name)

    @property
    def value(self) -> float:
        """Width divided by height, for arithmetic."""
        return self.width / self.height

    @property
    def display(self) -> str:
        """Human-friendly presentation string, e.g. 'Portrait (4:5)'."""
        return f"{self.label} ({self.name})"


PORTRAIT = AspectRatio("4:5", 1080, 1350, label="Portrait")
SQUARE = AspectRatio("1:1", 1080, 1080, label="Square")
LANDSCAPE = AspectRatio("1.91:1", 1080, 566, label="Landscape")

# Insertion order is presentation order: narrowest to widest. Do not sort
# this -- callers rely on iteration/dict order to drive UI ordering.
RATIOS: dict[str, AspectRatio] = {r.name: r for r in (PORTRAIT, SQUARE, LANDSCAPE)}
DEFAULT_RATIO = PORTRAIT

MIN_SECTIONS = 2

MAX_PERCENT = 40.0

_HEX = re.compile(r"\A#(?:[0-9a-f]{3}|[0-9a-f]{6})\Z")


def parse_colour(value: str) -> str:
    """Normalise a colour to lowercase `#rrggbb`.

    One parser, shared by `FrameStyle`, the CLI and the GUI's settings
    loader, so a colour is validated once at the boundary and can never
    reach PIL malformed. Accepts an optional leading `#` and the three-digit
    shorthand, because both are what people actually type.
    """
    text = str(value).strip().lower()
    if text and not text.startswith("#"):
        text = "#" + text
    if not _HEX.match(text):
        raise ValueError(f"invalid colour {value!r}: expected a hex colour like #ffffff")
    if len(text) == 4:
        text = "#" + "".join(character * 2 for character in text[1:])
    return text


def _check_percent(name: str, value: float) -> float:
    """Reject a width that is not a finite percent in range, naming the field."""
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= MAX_PERCENT:
        raise ValueError(f"{name} percent must be between 0 and {MAX_PERCENT:g}, got {value!r}")
    return number


def _to_rgb(colour: str) -> tuple[int, int, int]:
    """Split a normalised `#rrggbb` string into the tuple PIL wants."""
    return (int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16))


@dataclass(frozen=True)
class FrameStyle:
    """How much border to leave, and what colour to leave it.

    Widths are a percent of the frame's *short* side rather than absolute
    pixels, so one setting looks the same at 4:5 and at 1.91:1 -- a fixed
    100px border is a modest edge on a 1350px-tall frame and a heavy one on
    a 566px-tall frame. The style is always passed as an argument, never
    read from module state, so a batch run and a preview cannot disagree
    about it.
    """

    border_percent: float = 9.0
    border_colour: str = "#ffffff"
    gutter_percent: float = 4.0
    gutter_colour: str = "#ffffff"
    border_detail_frames: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "border_percent", _check_percent("border", self.border_percent))
        object.__setattr__(self, "gutter_percent", _check_percent("gutter", self.gutter_percent))
        object.__setattr__(self, "border_colour", parse_colour(self.border_colour))
        object.__setattr__(self, "gutter_colour", parse_colour(self.gutter_colour))

    def _resolve(self, percent: float, ratio: AspectRatio) -> int:
        return math.floor(percent / 100 * min(ratio.width, ratio.height) + 0.5)

    def border_px(self, ratio: AspectRatio) -> int:
        """The border, in output pixels, for this ratio."""
        return self._resolve(self.border_percent, ratio)

    def gutter_px(self, ratio: AspectRatio) -> int:
        """The gap between adjacent composite panels, in output pixels."""
        return self._resolve(self.gutter_percent, ratio)

    @property
    def border_rgb(self) -> tuple[int, int, int]:
        """The border colour as an RGB tuple, ready for `Image.new`."""
        return _to_rgb(self.border_colour)

    @property
    def gutter_rgb(self) -> tuple[int, int, int]:
        """The gutter colour as an RGB tuple, ready for `Image.new`."""
        return _to_rgb(self.gutter_colour)


DEFAULT_STYLE = FrameStyle()


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


def make_padded_frame(
    image: Image.Image,
    ratio: AspectRatio,
    style: FrameStyle = DEFAULT_STYLE,
) -> Image.Image:
    """Fit a panorama inside a canvas of the target ratio, inset by the style's border.

    The border describes the finished frame, in output pixels, on whichever
    axis binds -- not the source image. The panorama is scaled (preserving
    its own aspect ratio) to fit inside a box inset by that border on all
    four sides, then centred on the full-size canvas.

    For a normal wide panorama the width binds, so the left and right
    margins are exactly the border and the vertical gap is whatever is left
    over -- usually much larger. That asymmetry is inherent: the panorama's
    aspect ratio does not match the frame's, and frame 1 must show the whole
    panorama uncropped, so the border cannot be made even without cropping
    content away.

    Scaling straight to the fitted size (rather than compositing at source
    scale and downscaling) also avoids building a huge intermediate canvas,
    which matters on multi-hundred-megapixel scans.
    """
    border = style.border_px(ratio)
    pano_width, pano_height = image.size
    box_width = max(1, ratio.width - 2 * border)
    box_height = max(1, ratio.height - 2 * border)
    scale = min(box_width / pano_width, box_height / pano_height)
    fitted_width = max(1, math.floor(pano_width * scale + 0.5))
    fitted_height = max(1, math.floor(pano_height * scale + 0.5))

    fitted = image.resize((fitted_width, fitted_height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (ratio.width, ratio.height), style.border_rgb)
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
