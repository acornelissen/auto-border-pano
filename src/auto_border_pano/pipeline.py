"""File I/O for panorama splitting.

This is the only module that touches the filesystem. It also owns the
output-filename contract, which the GUI depends on for previews.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from auto_border_pano import compose, geometry, layout

# These are the user's own large-format scans, not hostile downloads; the
# largest sample is 132MP against Pillow's ~178MP default. Lifting the guard
# stops a legitimate scan being reported as a corrupt file. Malformed input
# is still caught by the per-file exception handling in process_folder.
Image.MAX_IMAGE_PIXELS = None

# Re-exported so cli.py and gui.py can offer ratio selection without
# importing geometry directly -- they depend on pipeline only.
AspectRatio = geometry.AspectRatio
RATIOS = geometry.RATIOS
DEFAULT_RATIO = geometry.DEFAULT_RATIO

JPEG_QUALITY = 95
JPEG_EXTENSIONS = (".jpg", ".jpeg")

PADDED_SUFFIX = "_1_padded.jpg"

ProgressCallback = Callable[[int, int, Path], None]


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
) -> list[Path]:
    """Split one panorama into a whole-panorama frame plus detail frames."""
    with Image.open(input_path) as opened:
        source = opened.convert("RGB")

    width, height = source.size
    if width < height:
        raise ValueError(
            f"{input_path} is portrait ({width}x{height}); "
            "auto-border-pano expects a landscape panorama"
        )

    count = geometry.section_count(width, height, ratio)
    targets = output_paths(output_prefix, count)
    targets[0].parent.mkdir(parents=True, exist_ok=True)

    geometry.make_padded_frame(source, ratio).save(targets[0], "JPEG", quality=JPEG_QUALITY)
    for index in range(count):
        geometry.make_section(source, index, count, ratio).save(
            targets[index + 1], "JPEG", quality=JPEG_QUALITY
        )
    return targets


COMPOSITE_SUFFIXES = {2: "_diptych.jpg", 3: "_triptych.jpg"}


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
) -> tuple[Image.Image, str]:
    """Solve and render a composite in memory, without writing anything.

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
    solved = layout.solve(aspects, ratio, geometry.SIDE_PADDING, layout.GUTTER)

    images = [_load_for_box(path, box) for path, box in zip(paths, solved.boxes, strict=True)]
    canvas = compose.render(images, solved, ratio)
    return canvas, solved.name


def compose_images(
    input_paths: Sequence[Path | str],
    output_prefix: Path | str,
    ratio: AspectRatio = DEFAULT_RATIO,
) -> CompositeResult:
    """Compose two or three images into one frame at the target ratio."""
    canvas, layout_name = compose_preview(input_paths, ratio)

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
) -> BatchResult:
    """Split every panorama in a folder.

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
            written = process_image(source, prefix, ratio)
        except Exception as error:
            result.failed.append((source, str(error)))
        else:
            result.written.extend(written)
            result.last_prefix = prefix
            result.last_count = len(written) - 1
            result.succeeded_count += 1
    return result
