"""File I/O for panorama splitting.

This is the only module that touches the filesystem. It also owns the
output-filename contract, which the GUI depends on for previews.
"""

from collections.abc import Callable
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
        geometry.make_section(source, index).save(
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
    on_progress: ProgressCallback | None = None,
) -> list[Path]:
    """Split every panorama in a folder.

    Individual failures are skipped so one unreadable file cannot abort a
    long batch. `on_progress` is called before each file with
    (completed_count, total_count, path).
    """
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    sources = find_panoramas(input_folder)
    written: list[Path] = []

    for done, source in enumerate(sources):
        if on_progress is not None:
            on_progress(done, len(sources), source)
        try:
            written.extend(process_image(source, output_folder / source.stem))
        except (OSError, ValueError) as error:
            print(f"Error processing {source}: {error}")
    return written
