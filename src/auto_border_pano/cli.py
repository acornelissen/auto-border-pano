"""Command-line entry points."""

import argparse
import sys
from pathlib import Path

from auto_border_pano import pipeline


def _ratio_type(value: str) -> pipeline.AspectRatio:
    """Resolve a --ratio argument, accepting a bare name ("4:5") or a label
    ("portrait"), case-insensitively.

    Raises argparse.ArgumentTypeError on an unknown value so argparse's own
    error path produces a clean, non-zero-exit message.
    """
    lowered = value.strip().lower()
    for ratio in pipeline.RATIOS.values():
        if lowered == ratio.name.lower() or lowered == ratio.label.lower():
            return ratio
    options = ", ".join(f"{r.label.lower()}|{r.name}" for r in pipeline.RATIOS.values())
    raise argparse.ArgumentTypeError(f"invalid ratio '{value}' (choose from {options})")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pano-split",
        description=(
            "Split a panorama into a whole-panorama frame plus zoomed detail "
            "frames, sized for an Instagram carousel. Accepts a single image "
            "or a folder of images."
        ),
    )
    parser.add_argument("input", type=Path, help="input image or folder")
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        default=Path("output"),
        help="output prefix for a single image, or output folder",
    )
    options = ", ".join(f"{r.label.lower()}|{r.name}" for r in pipeline.RATIOS.values())
    parser.add_argument(
        "--ratio",
        type=_ratio_type,
        default=pipeline.DEFAULT_RATIO,
        metavar="RATIO",
        help=(
            f"target aspect ratio for every frame: {options} "
            f"(default: {pipeline.DEFAULT_RATIO.label.lower()}). The number "
            "of detail frames is derived from this."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ratio = args.ratio

    if not args.input.exists():
        print(f"Error: '{args.input}' not found", file=sys.stderr)
        return 1

    try:
        if args.input.is_dir():
            if not pipeline.find_panoramas(args.input):
                print(f"No JPG files found in '{args.input}'")
                return 0
            result = pipeline.process_folder(args.input, args.output, ratio)
            print(
                f"Wrote {result.succeeded_count} of {result.total_count} "
                f"images to {args.output} at {ratio.display}"
            )
            for source, message in result.failed:
                print(f"Error processing {source}: {message}", file=sys.stderr)
            if result.failed:
                return 1
        else:
            written = pipeline.process_image(args.input, args.output, ratio)
            print(f"Wrote {len(written) - 1} detail frames at {ratio.display}")
            for path in written:
                print(f"  {path}")
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


def gui_main() -> int:
    """Launch the GUI, explaining clearly if tkinter is unavailable.

    The guard lives here rather than at module scope in gui.py so that
    importing the package can never terminate the host process.
    """
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print(
            "Error: tkinter is not available.\n\n"
            "tkinter is required for the GUI.\n"
            "  macOS (Homebrew):  brew install python-tk\n"
            "  Ubuntu/Debian:     sudo apt-get install python3-tk\n"
            "  Fedora:            sudo dnf install python3-tkinter\n"
            "  Arch:              sudo pacman -S tk\n"
            "  SUSE:              sudo zypper install python3-tk\n\n"
            "Alternatively use the command-line version: pano-split --help",
            file=sys.stderr,
        )
        return 1
    from auto_border_pano.gui import run

    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
