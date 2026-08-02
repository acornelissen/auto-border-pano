"""File I/O for panorama splitting.

This is the only module that touches the filesystem. It also owns the
output-filename contract, which the GUI depends on for previews.
"""

import logging
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock

from PIL import Image

from maskingframe import compose, geometry, layout

# These are the user's own large-format scans, not hostile downloads; the
# largest sample is 132MP against Pillow's ~178MP default. Lifting the guard
# stops a legitimate scan being reported as a corrupt file. Malformed input
# is still caught by the per-file exception handling in process_folder.
Image.MAX_IMAGE_PIXELS = None

# Re-exported so `cli.py` and `gui/` can offer ratio, border and position
# controls without importing `geometry` directly -- that is what preserves
# the one-way dependency direction. Do not "simplify" these away.
AspectRatio = geometry.AspectRatio
RATIOS = geometry.RATIOS
DEFAULT_RATIO = geometry.DEFAULT_RATIO
FrameStyle = geometry.FrameStyle
DEFAULT_STYLE = geometry.DEFAULT_STYLE
parse_colour = geometry.parse_colour
MAX_PERCENT = geometry.MAX_PERCENT

# Re-exported for the same reason as the ratio and style names: `cli.py` and
# `gui/` must be able to state how many sources compose without importing
# `layout` directly, which the dependency direction forbids.
MIN_IMAGES = layout.MIN_PANELS
MAX_IMAGES = layout.MAX_PANELS

default_positions = geometry.default_positions
normalise_positions = geometry.normalise_positions
move_position = geometry.move_position
insert_position = geometry.insert_position
drop_position = geometry.drop_position
frame_width = geometry.frame_width
position_travel = geometry.position_travel

JPEG_QUALITY = 95
JPEG_EXTENSIONS = (".jpg", ".jpeg")

PADDED_SUFFIX = "_1_padded.jpg"

# Reports one *file* finishing in a batch: (completed_files, total_files, path).
ProgressCallback = Callable[[int, int, Path], None]

# Reports one *frame* of a single panorama landing on disk:
# (frame_index, total_frames, path_just_written), zero-based like
# ProgressCallback's completed count, so the GUI's existing
# `(done + 1) / total` progress arithmetic works unchanged. Distinct from
# ProgressCallback -- "frame 3 of 5" of one source, not "file 3 of 10".
FrameCallback = Callable[[int, int, Path], None]

_log = logging.getLogger(__name__)


def _report_frame(on_frame: FrameCallback | None, index: int, total: int, path: Path) -> None:
    """Hand one written frame to the caller's callback, never letting it break the run.

    The frame is already on disk by the time this runs. A GUI callback here
    crosses back to the main thread through `root.after`, which can fail for
    reasons that have nothing to do with the image -- a closed window, say.
    Letting that propagate would abandon the remaining frames and report a
    failed conversion for files that were written correctly, so the
    exception is swallowed. It is logged rather than discarded, so a real
    bug in a callback is still findable.
    """
    if on_frame is None:
        return
    try:
        on_frame(index, total, path)
    except Exception:
        _log.exception("frame progress callback failed for %s", path)


@dataclass
class BatchResult:
    """Outcome of processing every panorama in a folder.

    `written` holds every output file from every successfully processed
    source, in source order. `failed` holds one (source_path, error_message)
    entry per source that could not be processed. `last_prefix` and
    `last_count` describe the last successfully processed source, so callers
    can preview it without re-deriving the naming convention.
    """

    written: list[Path] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)
    last_prefix: Path | None = None
    last_count: int | None = None
    succeeded_count: int = 0

    @property
    def total_count(self) -> int:
        return self.succeeded_count + len(self.failed)


def output_paths(prefix: Path | str, count: int) -> list[Path]:
    """Return every output path for a prefix and detail-frame count.

    Frame 1 is the whole panorama; frames 2..count+1 are the detail frames.
    """
    prefix = Path(prefix)
    names = [PADDED_SUFFIX]
    names += [f"_{n + 1}_section{n}.jpg" for n in range(1, count + 1)]
    return [prefix.with_name(prefix.name + name) for name in names]


def process_image(
    input_path: Path | str,
    output_prefix: Path | str,
    ratio: AspectRatio = DEFAULT_RATIO,
    on_frame: FrameCallback | None = None,
    positions: Sequence[float] | None = None,
    style: FrameStyle = DEFAULT_STYLE,
) -> list[Path]:
    """Split one panorama into a whole-panorama frame plus detail frames.

    `style` is a parameter with a default rather than module state, so a
    preview and the run that follows it cannot disagree about the border.

    `positions` places each detail frame along the panorama: one left edge
    per frame, as a fraction of the width, ascending. Omitted, the frames
    are spread evenly, which is what the CLI and every batch run do -- a
    position is chosen by looking at one photograph.

    `on_frame` is called once per output file, immediately after that file
    is written, with (frame_index, total_frames, path). The index is
    zero-based, matching `process_folder`'s completed count. It fires for
    every frame including the whole-panorama one, in the same order as the
    returned list, and `total_frames` always equals that list's length -- so
    a caller can drive a progress bar or fill in a contact strip frame by
    frame. An exception raised by the callback is logged and swallowed:
    the frames are already on disk, and a display glitch must not turn a
    good conversion into a reported failure.
    """
    with Image.open(input_path) as opened:
        source = opened.convert("RGB")

    width, height = source.size
    if width < height:
        raise ValueError(
            f"{input_path} is portrait ({width}x{height}); "
            "maskingframe expects a landscape panorama"
        )

    places = (
        geometry.default_positions(width, height, ratio)
        if positions is None
        else geometry.normalise_positions(positions, width, height, ratio)
    )
    count = len(places)
    targets = output_paths(output_prefix, count)
    targets[0].parent.mkdir(parents=True, exist_ok=True)

    total = len(targets)
    geometry.make_padded_frame(source, ratio, style).save(targets[0], "JPEG", quality=JPEG_QUALITY)
    _report_frame(on_frame, 0, total, targets[0])
    for index, place in enumerate(places):
        geometry.make_section(source, place, ratio, style).save(
            targets[index + 1], "JPEG", quality=JPEG_QUALITY
        )
        _report_frame(on_frame, index + 1, total, targets[index + 1])
    return targets


# How large a decoded source the preview cache may hold, in pixels.
#
# A full decode of the user's largest scan is 132MP, about 400MB in RGB, and
# holding that so a slider release feels quick would be paying for it in the
# wrong currency. But a detail frame is *cut* from the source and scaled up
# to the ratio's full width, so a copy bounded too hard comes out visibly
# soft. That fixes the floor: with `count` detail frames the copy must be at
# least `count * ratio.width` wide and `ratio.height` tall.
#
# `count` is roughly the source's aspect over the ratio's, so for a copy of
# P pixels at aspect A the width is sqrt(P*A) and the requirement
# sqrt(P*A) * ratio.value / A >= ratio.width reduces to
# P >= (ratio.height)^2 * A. The worst ratio is Portrait (1350 tall), so a
# 13:1 panorama -- wider than anything this tool has been pointed at, its
# own samples being 2.33:1 -- needs 23.7MP. 28MP clears that with room, and
# costs about 84MB rather than 400MB. `test_the_bound_never_softens_a_detail
# _frame` checks the arithmetic against the real `section_count`.
PREVIEW_MAX_PIXELS = 28_000_000


def preview_source_size(width: int, height: int) -> tuple[int, int]:
    """The size a source of this shape is cached at. Pure arithmetic.

    Only ever shrinks: a source already inside the bound is cached exactly
    as it was decoded, so a preview of it is the same picture a written run
    would cut.
    """
    pixels = width * height
    if pixels <= PREVIEW_MAX_PIXELS:
        return width, height
    scale = (PREVIEW_MAX_PIXELS / pixels) ** 0.5
    return max(1, int(width * scale)), max(1, int(height * scale))


_PreviewKey = tuple[str, int, int]

_preview_key: _PreviewKey | None = None
_preview_image: Image.Image | None = None
_preview_lock = Lock()


def _preview_cache_key(path: Path) -> _PreviewKey:
    """Path, modification time and size together.

    The path alone would go on showing the old picture for as long as the
    app stayed open if the file were re-exported under the same name.
    """
    stat = path.stat()
    return (str(path.resolve()), stat.st_mtime_ns, stat.st_size)


def clear_preview_cache() -> None:
    """Forget the decoded source. For tests, and for shutting down."""
    global _preview_key, _preview_image
    with _preview_lock:
        _preview_key = None
        _preview_image = None


def cached_preview_source(input_path: Path | str) -> Image.Image:
    """Decode a source for on-screen use, keeping the last one decoded.

    Only the preview may use this. Anything that writes to disk goes on
    opening the full-resolution original, because the copy here is bounded
    to `PREVIEW_MAX_PIXELS` and a file on disk must never be cut from a
    bounded copy.

    One entry, not a dictionary: a user works on one source at a time, and
    the point is to spare the *second* render of the *same* file, not to
    accumulate decodes. Guarded by a lock because previews run on worker
    threads.
    """
    global _preview_key, _preview_image
    path = Path(input_path)
    key = _preview_cache_key(path)
    with _preview_lock:
        if key == _preview_key and _preview_image is not None:
            return _preview_image

    with Image.open(path) as opened:
        target = preview_source_size(*opened.size)
        # libjpeg can decode straight to a reduced DCT scale, which is far
        # cheaper than decoding in full and throwing the pixels away. A
        # no-op for other formats and for anything already small enough.
        opened.draft("RGB", target)
        image = opened.convert("RGB")
    if image.width > target[0] or image.height > target[1]:
        image = image.resize(target, Image.Resampling.LANCZOS)

    with _preview_lock:
        _preview_key = key
        _preview_image = image
    return image


def ribbon_thumbnail(input_path: Path | str, max_width: int = 1200) -> Image.Image:
    """A small copy of the whole panorama, for the ribbon to draw.

    Bounded by width rather than by pixels because the ribbon is one long
    strip: a 13:1 panorama at 1200px wide is under 100px tall and costs
    almost nothing. Uses `draft` so libjpeg decodes straight to a reduced
    scale rather than decoding in full and throwing the pixels away.

    Separate from `cached_preview_source`, which holds a much larger copy
    for cutting detail frames from. This one is only ever looked at.
    """
    path = Path(input_path)
    with Image.open(path) as opened:
        width, height = opened.size
        if width > max_width:
            scale = max_width / width
            opened.draft("RGB", (max_width, max(1, math.floor(height * scale + 0.5))))
        image = opened.convert("RGB")
    if image.width > max_width:
        scale = max_width / image.width
        image = image.resize(
            (max_width, max(1, math.floor(image.height * scale + 0.5))),
            Image.Resampling.LANCZOS,
        )
    return image


def preview_frames(
    input_path: Path | str,
    ratio: AspectRatio = DEFAULT_RATIO,
    style: FrameStyle = DEFAULT_STYLE,
    cached: bool = False,
    positions: Sequence[float] | None = None,
) -> list[Image.Image]:
    """Render every frame in memory, without writing anything.

    `cached` lets the on-screen preview render from `cached_preview_source`
    rather than decoding the file again -- which is what makes re-rendering
    on a slider release bearable on a 132MP scan. It is off by default so
    that nothing acquires the bounded copy by accident; the CLI and every
    written run read the original in full.

    `style` is a parameter with a default rather than module state, so the
    preview shows the same border the run will write.

    The same split `process_image` performs, stopping short of saving, so a
    user can see what a ratio will do to a panorama before committing it to
    disk. `compose_preview` is the equivalent on the composite side.

    Cheap despite the name: each frame comes out at the target ratio's own
    size, not the source's, so previewing a 132MP scan holds a handful of
    ~1080px images rather than a copy of the scan per frame.
    """
    if cached:
        source = cached_preview_source(input_path)
    else:
        with Image.open(input_path) as opened:
            source = opened.convert("RGB")

    width, height = source.size
    if width < height:
        raise ValueError(
            f"{input_path} is portrait ({width}x{height}); "
            "maskingframe expects a landscape panorama"
        )

    places = (
        geometry.default_positions(width, height, ratio)
        if positions is None
        else geometry.normalise_positions(positions, width, height, ratio)
    )
    frames = [geometry.make_padded_frame(source, ratio, style)]
    frames += [geometry.make_section(source, place, ratio, style) for place in places]
    return frames


# One entry per composable count. `test_every_composable_count_has_a_filename`
# holds this to exactly MIN_IMAGES..MAX_IMAGES, so raising the ceiling cannot
# leave a count with nowhere to write to.
COMPOSITE_SUFFIXES = {
    2: "_diptych.jpg",
    3: "_triptych.jpg",
    4: "_tetraptych.jpg",
    5: "_pentaptych.jpg",
    6: "_hexaptych.jpg",
}


@dataclass(frozen=True)
class SourceFacts:
    """What a source is, and what the current ratio will do to it.

    Everything the interface needs to state a consequence before the user
    commits to it, rather than reporting it afterwards in the past tense.
    """

    width: int
    height: int
    native_ratio: str
    frame_count: int
    positions: tuple[float, ...] = ()
    """Where the detail frames land by default: one left edge per frame, as
    a fraction of the panorama's width. The interface opens on these and
    the user moves them from there."""

    window_fraction: float = 0.0
    """How much of the panorama's width one detail frame covers. The ribbon
    needs it to draw a window, and it is derived from the ratio and the
    source's height, so it belongs with the rest of the header read."""


def inspect_source(path: Path | str, ratio: AspectRatio = DEFAULT_RATIO) -> SourceFacts:
    """Read a source's shape without decoding it.

    This runs on every file selection, and the user's own scans reach
    132MP, so it must stay a header read -- `Image.open` is lazy and
    `.size` never triggers `load()`. Decoding here would stall the GUI on
    exactly the files it most needs to stay responsive for.

    `frame_count` counts every file that will appear on disk, the whole
    panorama included, so the button's number and the user's folder agree.
    """
    with Image.open(path) as opened:
        width, height = opened.size
    return SourceFacts(
        width=width,
        height=height,
        native_ratio=f"{width / height:.2f}:1",
        frame_count=geometry.section_count(width, height, ratio) + 1,
        positions=geometry.default_positions(width, height, ratio),
        window_fraction=min(1.0, geometry.frame_width(height, ratio) / width),
    )


def name_layout(
    input_paths: Sequence[Path | str],
    ratio: AspectRatio = DEFAULT_RATIO,
    style: FrameStyle = DEFAULT_STYLE,
) -> str:
    """Name the arrangement these sources will get, without rendering it.

    `style` is a parameter with a default rather than module state: a wide
    gutter can change which arrangement wins, so the name must be solved
    with the same style the render will use.

    The solver only needs each source's aspect ratio, so this reads headers
    and stops. `compose_preview` renders through the same `layout.solve`
    call, which is what keeps the name shown in the rail and the name shown
    under the finished composite from ever disagreeing.
    """
    paths = [Path(p) for p in input_paths]
    if len(paths) not in COMPOSITE_SUFFIXES:
        raise ValueError(f"expected {MIN_IMAGES} to {MAX_IMAGES} images, got {len(paths)}")

    aspects = []
    for path in paths:
        with Image.open(path) as opened:
            width, height = opened.size
        aspects.append(width / height)
    return layout.solve(aspects, ratio, style).name


NormalisedRect = tuple[float, float, float, float]
"""(x, y, width, height) as fractions of the output frame, 0..1 on both axes."""


@dataclass(frozen=True)
class CompositeRects:
    """Where a composite's panels and gaps land, as fractions of the frame.

    Plain floats rather than `layout.Box` objects, and the point of that is
    architectural: the GUI may import `pipeline` and nothing else from the
    package, so a live preview of the gaps has to be handed the arithmetic
    already done. Normalised rather than in pixels for the same sort of
    reason -- a preview drawn at whatever size a window allows should not
    have to know what the output resolution is.
    """

    panels: tuple[NormalisedRect, ...]
    gaps: tuple[NormalisedRect, ...]
    name: str


def composite_rects(
    aspects: Sequence[float],
    ratio: AspectRatio = DEFAULT_RATIO,
    style: FrameStyle = DEFAULT_STYLE,
) -> CompositeRects:
    """Solve a composite's arrangement from aspect ratios alone.

    Takes the sources' aspect ratios as floats, not paths, and opens
    nothing: this is pure arithmetic, so an interface can call it on every
    slider move without going near a worker thread. Anything that needs a
    file's shape has read it already -- the user's scans reach 132MP and a
    header read on the GUI thread is exactly what stalls those.

    Solves through the same `layout.solve` the render uses, so a previewed
    arrangement and a saved one cannot disagree.
    """

    def normalise(box: layout.Box) -> NormalisedRect:
        return (
            box.x / ratio.width,
            box.y / ratio.height,
            box.width / ratio.width,
            box.height / ratio.height,
        )

    solved = layout.solve(aspects, ratio, style)
    return CompositeRects(
        panels=tuple(normalise(box) for box in solved.boxes),
        gaps=tuple(normalise(box) for box in solved.gutters),
        name=solved.name,
    )


@dataclass(frozen=True)
class CompositeResult:
    """Where a composite was written, and which arrangement won.

    The layout name is carried back so the GUI can show the automatic
    decision rather than leaving it mysterious.
    """

    path: Path
    layout_name: str


# Draft/thumbnail toward this multiple of a panel's own solved box before the
# final exact resize in compose.render. Large enough that any source already
# within this margin of its box is left untouched -- so this only trims
# memory for sources meaningfully bigger than what they'll render at, and
# never touches the pixels the final resize sees for anything else.
_DOWNSCALE_MARGIN = 6


def _load_for_box(path: Path, box: layout.Box) -> Image.Image:
    """Open one composite source, decoded no larger than it needs to be.

    `compose_images` used to hold every source at full scan resolution
    simultaneously, which peaked at gigabytes of RSS for large photos.
    Nothing downstream needs more detail than `_DOWNSCALE_MARGIN` times the
    panel's own box, so shrink toward that here: `Image.draft` lets libjpeg
    decode at a reduced DCT scale up front (a no-op for non-JPEG sources,
    and for sources already near the target), and `thumbnail` finishes with
    a real LANCZOS reduction if draft didn't get all the way there. Both
    only ever shrink, never grow, so a source already at or below the
    margin is returned untouched -- and `compose.render` still does its own
    exact resize to the box afterwards, so output quality is unaffected.
    """
    target = (box.width * _DOWNSCALE_MARGIN, box.height * _DOWNSCALE_MARGIN)
    with Image.open(path) as opened:
        opened.draft("RGB", target)
        image = opened.convert("RGB")
    if image.width > target[0] or image.height > target[1]:
        image.thumbnail(target, Image.Resampling.LANCZOS)
    return image


def compose_preview(
    input_paths: Sequence[Path | str],
    ratio: AspectRatio = DEFAULT_RATIO,
    style: FrameStyle = DEFAULT_STYLE,
) -> tuple[Image.Image, str]:
    """Solve and render a composite in memory, without writing anything.

    `style` is a parameter with a default rather than module state, so the
    preview and the saved composite cannot disagree about border or gutter.

    Returns the rendered image and the name of the winning layout, so the
    GUI can let a user compare arrangements before committing one to disk.
    `compose_images` is a thin wrapper around this that also saves the
    result, so there is exactly one solve-and-render path.
    """
    paths = [Path(p) for p in input_paths]
    if len(paths) not in COMPOSITE_SUFFIXES:
        raise ValueError(f"expected {MIN_IMAGES} to {MAX_IMAGES} images, got {len(paths)}")

    with_sizes = []
    for path in paths:
        with Image.open(path) as opened:
            with_sizes.append(opened.size)

    aspects = [width / height for width, height in with_sizes]
    solved = layout.solve(aspects, ratio, style)

    images = [_load_for_box(path, box) for path, box in zip(paths, solved.boxes, strict=True)]
    canvas = compose.render(images, solved, ratio, style)
    return canvas, solved.name


def compose_images(
    input_paths: Sequence[Path | str],
    output_prefix: Path | str,
    ratio: AspectRatio = DEFAULT_RATIO,
    style: FrameStyle = DEFAULT_STYLE,
) -> CompositeResult:
    """Compose two or three images into one frame at the target ratio.

    `style` is a parameter with a default rather than module state, so a run
    and the preview it followed cannot disagree about border or gutter.
    """
    canvas, layout_name = compose_preview(input_paths, ratio, style)

    prefix = Path(output_prefix)
    target = prefix.with_name(prefix.name + COMPOSITE_SUFFIXES[len(input_paths)])
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target, "JPEG", quality=JPEG_QUALITY)
    return CompositeResult(target, layout_name)


def find_panoramas(folder: Path | str) -> list[Path]:
    """Return every JPEG in a folder, case-insensitively, without duplicates."""
    return sorted(
        path
        for path in Path(folder).iterdir()
        if path.is_file() and path.suffix.lower() in JPEG_EXTENSIONS
    )


def process_folder(
    input_folder: Path | str,
    output_folder: Path | str,
    ratio: AspectRatio = DEFAULT_RATIO,
    on_progress: ProgressCallback | None = None,
    style: FrameStyle = DEFAULT_STYLE,
) -> BatchResult:
    """Split every panorama in a folder.

    `style` is a parameter with a default rather than module state, so every
    file in a batch is framed exactly as the preview promised.

    Individual failures are skipped so one unreadable or non-landscape file
    cannot abort a long batch. `on_progress` is called before each file with
    (completed_count, total_count, path). Failures are reported via the
    returned `BatchResult.failed`; the caller owns how they are surfaced.
    """
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    sources = find_panoramas(input_folder)
    result = BatchResult()

    for done, source in enumerate(sources):
        if on_progress is not None:
            on_progress(done, len(sources), source)
        prefix = output_folder / source.stem
        try:
            written = process_image(source, prefix, ratio, None, style=style)
        except Exception as error:
            result.failed.append((source, str(error)))
        else:
            result.written.extend(written)
            result.last_prefix = prefix
            result.last_count = len(written) - 1
            result.succeeded_count += 1
    return result
