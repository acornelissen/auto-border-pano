"""Command-line entry points."""

import argparse
import sys
from pathlib import Path

from auto_border_pano import pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pano-split",
        description=(
            "Split a panorama into a padded square plus three 1080x1080 "
            "sections. Accepts a single image or a folder of images."
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.input.exists():
        print(f"Error: '{args.input}' not found", file=sys.stderr)
        return 1

    try:
        if args.input.is_dir():
            written = pipeline.process_folder(args.input, args.output)
            print(f"Wrote {len(written)} files to {args.output}")
        else:
            for path in pipeline.process_image(args.input, args.output):
                print(f"Wrote {path}")
    except (OSError, ValueError) as error:
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
    from auto_border_pano.gui import run  # type: ignore[import-untyped]
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
