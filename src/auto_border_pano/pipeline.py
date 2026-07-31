"""File I/O for panorama splitting.

This is the only module that touches the filesystem. It also owns the
output-filename contract, which the GUI depends on for previews.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from auto_border_pano import geometry

JPEG_QUALITY = 95
JPEG_EXTENSIONS = (".jpg", ".jpeg")

OUTPUT_SUFFIXES = (
    "_1_padded_square.jpg",
    "_2_section1.jpg",
    "_3_section2.jpg",
    "_4_section3.jpg",
)

ProgressCallback = Callable[[int, int, Path], None]


@dataclass
class BatchResult:
    """Outcome of processing every panorama in a folder.

    `written` holds every output file from every successfully processed
    source, in source order. `failed` holds one (source_path, error_message)
    entry per source that could not be processed. `last_prefix` is the
    output prefix (as passed to `output_paths`) of the last successfully
    processed source, or `None` if nothing succeeded; callers that want a
    preview of the batch's result should use this rather than re-deriving
    the naming convention themselves.
    """

    written: list[Path] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)
    last_prefix: Path | None = None

    @property
    def succeeded_count(self) -> int:
        return len(self.written) // len(OUTPUT_SUFFIXES)

    @property
    def total_count(self) -> int:
        return self.succeeded_count + len(self.failed)


def output_paths(prefix: Path | str) -> list[Path]:
    """Return the four output paths produced for a given prefix."""
    prefix = Path(prefix)
    return [prefix.with_name(prefix.name + suffix) for suffix in OUTPUT_SUFFIXES]


def process_image(input_path: Path | str, output_prefix: Path | str) -> list[Path]:
    """Split one panorama into its four outputs and return their paths."""
    targets = output_paths(output_prefix)
    targets[0].parent.mkdir(parents=True, exist_ok=True)

    with Image.open(input_path) as opened:
        source = opened.convert("RGB")

    geometry.make_padded_square(source).save(targets[0], "JPEG", quality=JPEG_QUALITY)
    for index in range(geometry.SECTION_COUNT):
        geometry.make_section(source, index).save(targets[index + 1], "JPEG", quality=JPEG_QUALITY)
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
    on_progress: ProgressCallback | None = None,
) -> BatchResult:
    """Split every panorama in a folder.

    Individual failures are skipped so one unreadable file cannot abort a
    long batch. `on_progress` is called before each file with
    (completed_count, total_count, path). Failures are reported to the
    caller via the returned `BatchResult.failed` rather than printed here;
    the caller (CLI, GUI, ...) owns how failures are surfaced.
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
            result.written.extend(process_image(source, prefix))
        except (OSError, ValueError) as error:
            result.failed.append((source, str(error)))
        else:
            result.last_prefix = prefix
    return result
