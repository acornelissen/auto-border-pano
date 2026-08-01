"""File I/O for panorama splitting.

This is the only module that touches the filesystem. It also owns the
output-filename contract, which the GUI depends on for previews.
"""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from maskingframe import compose, geometry, layout

# These are the user's own large-format scans, not hostile downloads; the
# largest sample is 132MP against Pillow's ~178MP default. Lifting the guard
# stops a legitimate scan being reported as a corrupt file. Malformed input
# is still caught by the per-file exception handling in process_folder.
Image.MAX_IMAGE_PIXELS = None

# Re-exported so cli.py and gui/ can offer ratio and border selection
# without importing geometry directly -- they depend on pipeline only.
AspectRatio = geometry.AspectRatio
RATIOS = geometry.RATIOS
DEFAULT_RATIO = geometry.DEFAULT_RATIO
FrameStyle = geometry.FrameStyle
DEFAULT_STYLE = geometry.DEFAULT_STYLE
parse_colour = geometry.parse_colour
MAX_PERCENT = geometry.MAX_PERCENT

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
    style: FrameStyle = DEFAULT_STYLE,
) -> list[Path]:
    """Split one panorama into a whole-panorama frame plus detail frames.

    `style` is a parameter with a default rather than module state, so a
    preview and the run that follows it cannot disagree about the border.

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

    count = geometry.section_count(width, height, ratio)
    targets = output_paths(output_prefix, count)
    targets[0].parent.mkdir(parents=True, exist_ok=True)

    total = len(targets)
    geometry.make_padded_frame(source, ratio, style).save(targets[0], "JPEG", quality=JPEG_QUALITY)
    _report_frame(on_frame, 0, total, targets[0])
    for index in range(count):
        geometry.make_section(source, index, count, ratio, style).save(
            targets[index + 1], "JPEG", quality=JPEG_QUALITY
        )
        _report_frame(on_frame, index + 1, total, targets[index + 1])
    return targets


def preview_frames(
    input_path: Path | str,
    ratio: AspectRatio = DEFAULT_RATIO,
    style: FrameStyle = DEFAULT_STYLE,
) -> list[Image.Image]:
    """Render every frame in memory, without writing anything.

    `style` is a parameter with a default rather than module state, so the
    preview shows the same border the run will write.

    The same split `process_image` performs, stopping short of saving, so a
    user can see what a ratio will do to a panorama before committing it to
    disk. `compose_preview` is the equivalent on the composite side.

    Cheap despite the name: each frame comes out at the target ratio's own
    size, not the source's, so previewing a 132MP scan holds a handful of
    ~1080px images rather than a copy of the scan per frame.
    """
    with Image.open(input_path) as opened:
        source = opened.convert("RGB")

    width, height = source.size
    if width < height:
        raise ValueError(
            f"{input_path} is portrait ({width}x{height}); "
            "maskingframe expects a landscape panorama"
        )

    count = geometry.section_count(width, height, ratio)
    frames = [geometry.make_padded_frame(source, ratio, style)]
    frames += [geometry.make_section(source, index, count, ratio, style) for index in range(count)]
    return frames


COMPOSITE_SUFFIXES = {2: "_diptych.jpg", 3: "_triptych.jpg"}


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
        raise ValueError(f"expected 2 or 3 images, got {len(paths)}")

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
        raise ValueError(f"expected 2 or 3 images, got {len(paths)}")

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
            written = process_image(source, prefix, ratio, None, style)
        except Exception as error:
            result.failed.append((source, str(error)))
        else:
            result.written.extend(written)
            result.last_prefix = prefix
            result.last_count = len(written) - 1
            result.succeeded_count += 1
    return result
