"""Pure image transforms.

Every function here takes and returns PIL Images. Nothing in this module
opens or writes a file, which is what makes it fast to test.
"""

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

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


def frame_width(pano_height: int, ratio: AspectRatio) -> int:
    """How wide one detail frame's crop is, in source pixels.

    A detail frame is a full-height crop at exactly the output aspect
    ratio, so nothing vertical is ever thrown away. The width deliberately
    does not depend on how many frames there are: once the frames are
    placed by hand, adding a sixth must not re-cut the first five.
    """
    return max(1, math.floor(pano_height * ratio.value + 0.5))


def position_travel(pano_width: int, pano_height: int, ratio: AspectRatio) -> float:
    """How far a frame's left edge may move, as a fraction of the width.

    Zero when the source is narrower than a single frame -- a 1.5:1 image
    at 1.91:1 -- in which case every frame is the whole width and there is
    nothing to choose. Degenerate, but it must not raise.
    """
    return max(0.0, 1.0 - frame_width(pano_height, ratio) / pano_width)


def clamp_position(position: float, pano_width: int, pano_height: int, ratio: AspectRatio) -> float:
    """Hold one position inside the travel, so no frame hangs off an edge."""
    return min(max(position, 0.0), position_travel(pano_width, pano_height, ratio))


def normalise_positions(
    positions: Sequence[float], pano_width: int, pano_height: int, ratio: AspectRatio
) -> tuple[float, ...]:
    """Clamp every position and hold the tuple ascending.

    Ascending, not sorted: a frame dragged past its neighbour stops at the
    neighbour rather than swapping with it. Sorting would renumber the
    carousel under the user's hand. Overlap is allowed -- two tight crops
    on one subject is a legitimate choice -- so this is a running maximum,
    not a minimum separation.
    """
    running = 0.0
    result: list[float] = []
    for position in positions:
        running = max(running, clamp_position(position, pano_width, pano_height, ratio))
        result.append(running)
    return tuple(result)


def default_positions(
    pano_width: int,
    pano_height: int,
    ratio: AspectRatio,
    count: int | None = None,
) -> tuple[float, ...]:
    """Evenly spaced frames: the first flush left, the last flush right.

    The count defaults to `section_count`, which is still the right first
    guess -- how many exact tiles fit across the panorama -- but it is only
    an opening position now, not a constraint.
    """
    if count is None:
        count = section_count(pano_width, pano_height, ratio)
    count = max(1, count)
    travel = position_travel(pano_width, pano_height, ratio)
    if count == 1:
        return (0.0,)
    return tuple(index * travel / (count - 1) for index in range(count))


def insert_position(
    positions: Sequence[float], pano_width: int, pano_height: int, ratio: AspectRatio
) -> tuple[float, ...]:
    """Add one frame where the panorama is least covered.

    A new frame should land on something nobody is looking at yet, so the
    widest stretch no frame covers wins and the frame is centred in it.
    When the frames already cover everything -- which they do as soon as
    they are close together -- there is no such stretch, so it falls back
    to halving the widest gap between two adjacent left edges.
    """
    width = frame_width(pano_height, ratio) / pano_width
    places = sorted(positions)
    if not places:
        return (0.0,)

    # Merge the covered intervals, then look at what is left over.
    merged: list[list[float]] = []
    for start in places:
        end = start + width
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    holes: list[tuple[float, float]] = []
    edge = 0.0
    for start, end in merged:
        if start > edge:
            holes.append((edge, start))
        edge = max(edge, end)
    if edge < 1.0:
        holes.append((edge, 1.0))

    if holes:
        start, end = max(holes, key=lambda hole: hole[1] - hole[0])
        chosen = (start + end) / 2 - width / 2
    else:
        gaps = list(pairwise(places))
        if gaps:
            start, end = max(gaps, key=lambda gap: gap[1] - gap[0])
            chosen = (start + end) / 2
        else:
            chosen = places[0]

    chosen = clamp_position(chosen, pano_width, pano_height, ratio)
    return normalise_positions(sorted([*places, chosen]), pano_width, pano_height, ratio)


def drop_position(positions: Sequence[float]) -> tuple[float, ...]:
    """Remove the last frame. Never goes below two.

    Two is the floor for the same reason `section_count` floors there: a
    single detail frame would just restate the whole-panorama frame.
    """
    if len(positions) <= MIN_SECTIONS:
        raise ValueError(f"a panorama keeps at least two detail frames, got {len(positions)}")
    return tuple(positions[:-1])


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


def section_bounds(
    pano_width: int, pano_height: int, position: float, ratio: AspectRatio
) -> tuple[int, int]:
    """The horizontal crop bounds of the detail frame at `position`.

    Full height and exactly the output aspect, so the cover-scale in
    `make_section` discards nothing vertically. `position` is the left edge
    as a fraction of the width; it is clamped, so a caller cannot ask for a
    crop that runs off an edge.
    """
    width = min(frame_width(pano_height, ratio), pano_width)
    clamped = clamp_position(position, pano_width, pano_height, ratio)
    start = math.floor(clamped * pano_width + 0.5)
    start = min(start, pano_width - width)
    return start, start + width


def make_section(
    image: Image.Image,
    position: float,
    ratio: AspectRatio,
    style: FrameStyle = DEFAULT_STYLE,
) -> Image.Image:
    """Crop one detail frame at `position` and scale it to fill the ratio.

    The crop is already the output aspect, so the cover-scale is close to a
    straight resize and the centre crop takes at most a rounding pixel.

    A detail frame is full-bleed by default: the border is what makes frame
    1 the establishing shot, and giving every frame one flattens that
    distinction. `style.border_detail_frames` turns it on for users who want
    the carousel to read as a single object, in which case the crop targets
    the inset box and the border is drawn around it.
    """
    border = style.border_px(ratio) if style.border_detail_frames else 0
    inner_width = max(1, ratio.width - 2 * border)
    inner_height = max(1, ratio.height - 2 * border)

    width, height = image.size
    start, end = section_bounds(width, height, position, ratio)
    crop = image.crop((start, 0, end, height))
    crop_width, crop_height = crop.size

    scale = max(inner_width / crop_width, inner_height / crop_height)
    # Half-up rounding of crop_dim * scale is what actually guarantees the
    # resized image covers the target on both axes. The max(inner_*, ...)
    # here is belt-and-braces, not load-bearing: it's a floor against any
    # future rounding change, not something exercised by current inputs.
    resized = crop.resize(
        (
            max(inner_width, math.floor(crop_width * scale + 0.5)),
            max(inner_height, math.floor(crop_height * scale + 0.5)),
        ),
        Image.Resampling.LANCZOS,
    )

    x_offset = (resized.width - inner_width) // 2
    y_offset = (resized.height - inner_height) // 2
    inner = resized.crop((x_offset, y_offset, x_offset + inner_width, y_offset + inner_height))
    if border == 0:
        return inner

    canvas = Image.new("RGB", (ratio.width, ratio.height), style.border_rgb)
    canvas.paste(inner, (border, border))
    return canvas
