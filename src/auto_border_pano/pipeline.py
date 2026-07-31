"""File I/O for panorama splitting.

This is the only module that touches the filesystem. It also owns the
output-filename contract, which the GUI depends on for previews.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from auto_border_pano import geometry

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

    geometry.make_padded_frame(source, ratio).save(
        targets[0], "JPEG", quality=JPEG_QUALITY
    )
    for index in range(count):
        geometry.make_section(source, index, count, ratio).save(
            targets[index + 1], "JPEG", quality=JPEG_QUALITY
        )
    return targets


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
