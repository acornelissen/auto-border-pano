"""Command-line entry points."""

import argparse
import sys
from pathlib import Path

from maskingframe import pipeline


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


def _percent_type(value: str) -> float:
    """Resolve a --border or --gutter argument, as a percent of the short side.

    Validated here rather than at render time so a typo fails immediately
    with argparse's own clean, non-zero-exit message.
    """
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid percent '{value}': expected a number") from None
    if not 0.0 <= number <= pipeline.MAX_PERCENT:
        raise argparse.ArgumentTypeError(
            f"invalid percent '{value}': must be between 0 and {pipeline.MAX_PERCENT:g}"
        )
    return number


def _colour_type(value: str) -> str:
    """Resolve a colour argument to a normalised #rrggbb string.

    Same reason as _percent_type: one parser at the boundary, so a bad
    colour can never reach PIL.
    """
    try:
        return pipeline.parse_colour(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from None


def _style_from_args(args: argparse.Namespace) -> pipeline.FrameStyle:
    """Assemble the frame style the run should use.

    Built once and passed down, rather than read from module state, so a
    single run cannot disagree with itself about the border.
    """
    return pipeline.FrameStyle(
        border_percent=args.border,
        border_colour=args.border_colour,
        gutter_percent=args.gutter,
        gutter_colour=args.gutter_colour,
        border_detail_frames=args.border_detail_frames,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="maskingframe",
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
    parser.add_argument(
        "--border",
        type=_percent_type,
        default=pipeline.DEFAULT_STYLE.border_percent,
        metavar="PERCENT",
        help=(
            "border width as a percent of the frame's short side "
            f"(default: {pipeline.DEFAULT_STYLE.border_percent:g})"
        ),
    )
    parser.add_argument(
        "--border-colour",
        "--border-color",
        dest="border_colour",
        type=_colour_type,
        default=pipeline.DEFAULT_STYLE.border_colour,
        metavar="HEX",
        help=f"border colour (default: {pipeline.DEFAULT_STYLE.border_colour})",
    )
    parser.add_argument(
        "--gutter",
        type=_percent_type,
        default=pipeline.DEFAULT_STYLE.gutter_percent,
        metavar="PERCENT",
        help=(
            "composites only: gap between panels, as a percent of the frame's "
            f"short side (default: {pipeline.DEFAULT_STYLE.gutter_percent:g})"
        ),
    )
    parser.add_argument(
        "--gutter-colour",
        "--gutter-color",
        dest="gutter_colour",
        type=_colour_type,
        default=pipeline.DEFAULT_STYLE.gutter_colour,
        metavar="HEX",
        help=(
            "composites only: colour of the gap between panels "
            f"(default: {pipeline.DEFAULT_STYLE.gutter_colour})"
        ),
    )
    parser.add_argument(
        "--border-detail-frames",
        action="store_true",
        help=(
            "draw the border around the zoomed detail frames too, not just the whole-panorama frame"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ratio = args.ratio
    style = _style_from_args(args)

    if not args.input.exists():
        print(f"Error: '{args.input}' not found", file=sys.stderr)
        return 1

    try:
        if args.input.is_dir():
            if not pipeline.find_panoramas(args.input):
                print(f"No JPG files found in '{args.input}'")
                return 0
            result = pipeline.process_folder(args.input, args.output, ratio, None, style)
            print(
                f"Wrote {result.succeeded_count} of {result.total_count} "
                f"images to {args.output} at {ratio.display}"
            )
            for source, message in result.failed:
                print(f"Error processing {source}: {message}", file=sys.stderr)
            if result.failed:
                return 1
        else:
            written = pipeline.process_image(args.input, args.output, ratio, None, style)
            print(f"Wrote {len(written) - 1} detail frames at {ratio.display}")
            for path in written:
                print(f"  {path}")
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


def gui_main() -> int:
    """Launch the GUI, explaining clearly if Qt is unavailable.

    The guard lives here rather than at module scope in the GUI package so
    that importing the package can never terminate the host process.
    """
    try:
        import PySide6  # noqa: F401
    except ImportError:
        print(
            "Error: PySide6 is not available.\n\n"
            "PySide6 provides the GUI. Install it with:\n"
            "  uv sync            (inside a checkout of this project)\n"
            "  pip install PySide6\n\n"
            "Alternatively use the command-line version: maskingframe --help",
            file=sys.stderr,
        )
        return 1
    from maskingframe.gui import run

    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
