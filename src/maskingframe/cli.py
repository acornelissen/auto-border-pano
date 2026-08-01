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


COMPOSE_COMMAND = "compose"


def _add_style_arguments(parser: argparse.ArgumentParser) -> None:
    """Attach the ratio and framing flags shared by both commands.

    Split and compose take exactly the same style, so they share one
    definition; that is what stops the two commands drifting apart in
    spelling, defaults, or help text.
    """
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
            "splits only: draw the border around the zoomed detail frames too, "
            "not just the whole-panorama frame"
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the split parser -- the bare, no-subcommand form.

    Split keeps the top level to itself rather than becoming a `split`
    subcommand, because `maskingframe pano.jpg out` has to keep working
    exactly as it always has.
    """
    parser = argparse.ArgumentParser(
        prog="maskingframe",
        description=(
            "Split a panorama into a whole-panorama frame plus zoomed detail "
            "frames, sized for an Instagram carousel. Accepts a single image "
            "or a folder of images. Use the 'compose' subcommand instead to "
            "join two or three images into a single diptych or triptych."
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
    _add_style_arguments(parser)
    return parser


def build_compose_parser() -> argparse.ArgumentParser:
    """Build the parser for `maskingframe compose`.

    The inputs are `nargs="+"` rather than two positionals with a third
    optional one: argparse cannot express "2 or 3" without silently
    mis-assigning arguments, so the count is checked afterwards where the
    error message can say how many were actually given.

    The output is a `-o` option, not a trailing positional, because a
    positional after a variable-length list is ambiguous -- argparse would
    have to guess whether the last path is a source or a destination.
    """
    parser = argparse.ArgumentParser(
        prog="maskingframe compose",
        description=(
            "Compose two or three images into a single frame at the target "
            "aspect ratio. The arrangement is chosen automatically, and any "
            "mix of orientations is accepted."
        ),
    )
    parser.add_argument("inputs", type=Path, nargs="+", metavar="IMAGE", help="two or three images")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("output"),
        help="output prefix; the suffix _diptych.jpg or _triptych.jpg is added",
    )
    _add_style_arguments(parser)
    return parser


def _compose_main(argv: list[str]) -> int:
    """Run the compose subcommand.

    No landscape check here: mixing orientations is the point of a
    composite, so portrait sources are perfectly valid.
    """
    parser = build_compose_parser()
    args = parser.parse_args(argv)

    if len(args.inputs) not in (2, 3):
        parser.error(f"expected 2 or 3 images, got {len(args.inputs)}")

    for path in args.inputs:
        if not path.exists():
            print(f"Error: '{path}' not found", file=sys.stderr)
            return 1

    try:
        result = pipeline.compose_images(
            args.inputs, args.output, args.ratio, _style_from_args(args)
        )
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(f"Wrote {result.path} as a {result.layout_name} at {args.ratio.display}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Dispatch on the literal first word rather than an argparse subparser,
    # so the bare `maskingframe pano.jpg out` form is untouched -- a
    # subparser would have made `input` compete with the command name.
    # A file named exactly "compose" in the current directory would be
    # shadowed; spell it "./compose" to split it.
    if argv and argv[0] == COMPOSE_COMMAND:
        return _compose_main(argv[1:])

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
