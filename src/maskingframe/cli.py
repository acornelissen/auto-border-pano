"""Command-line entry points."""

import argparse
import re
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
        padded_border_percent=args.frame1_border,
    )


COMPOSE_COMMAND = "compose"

_ARRANGEMENT = re.compile(r"^(?:[RC][0-9](?:\.[0-9])*|[RC]\(.+\))$", re.IGNORECASE)


def _arrangement(value: str) -> str:
    """Check the *spelling* here, not the arrangement.

    Whether an arrangement exists depends on how many sources there are,
    which argparse does not know: the inputs are `nargs="+"` and are counted
    afterwards. So a typo fails here with argparse's own message and a
    well-spelt name that no arrangement answers to fails in the run, where
    the count is known and can be named.
    """
    text = value.strip()
    if text and not _ARRANGEMENT.match(text):
        raise argparse.ArgumentTypeError(
            f"invalid arrangement '{value}': spell it like R2.2, "
            "or the long form 'R(C(1,2),C(3,4))' in quotes"
        )
    return text


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
        "--frame1-border",
        dest="frame1_border",
        type=_percent_type,
        default=None,
        metavar="PERCENT",
        help=(
            "splits only: give the whole-panorama frame its own border width, "
            "so it can fill more of the frame without changing what the border "
            "means for the detail frames or a composite (default: the same as "
            "--border)"
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
            "join two to six images into a single composite."
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
            "Compose two to six images into a single frame at the target "
            "aspect ratio. The arrangement is chosen automatically, and any "
            "mix of orientations is accepted."
        ),
    )
    parser.add_argument("inputs", type=Path, nargs="+", metavar="IMAGE", help="two to six images")
    parser.add_argument(
        "--arrangement",
        type=_arrangement,
        default="",
        help=(
            "force an arrangement instead of choosing the best fit, "
            "e.g. R2.2 (two columns of two). The long form needs quoting."
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("output"),
        help=(
            "output prefix; one of the suffixes "
            + ", ".join(
                pipeline.COMPOSITE_SUFFIXES[count] for count in sorted(pipeline.COMPOSITE_SUFFIXES)
            )
            + " is added"
        ),
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

    if not pipeline.MIN_IMAGES <= len(args.inputs) <= pipeline.MAX_IMAGES:
        parser.error(
            f"expected {pipeline.MIN_IMAGES} to {pipeline.MAX_IMAGES} images, "
            f"got {len(args.inputs)}"
        )

    for path in args.inputs:
        if not path.exists():
            print(f"Error: '{path}' not found", file=sys.stderr)
            return 1

    style = _style_from_args(args)

    try:
        result = pipeline.compose_images(
            args.inputs, args.output, args.ratio, args.arrangement, style=style
        )
    except ValueError as error:
        parser.error(str(error))
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    # No article before the arrangement: it used to be a slug that read as a
    # noun ("as a row-one-then-two"), and it is now notation, where "as a
    # R(1,C(2,3))" reads as a typo.
    print(f"Wrote {result.path} as {result.layout_name} at {args.ratio.display}")
    # The composite is already on disk, so nothing here may fail the run.
    # Naming the flag re-reads every source, and a source deleted in the
    # meantime would otherwise turn a successful write into a traceback.
    try:
        short = next(
            (
                option.short_name
                for option in pipeline.arrangements(args.inputs, args.ratio, style)
                if option.name == result.layout_name
            ),
            "",
        )
    except Exception:
        short = ""
    if short:
        print(f"  --arrangement {short}")
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
            written = pipeline.process_image(args.input, args.output, ratio, None, style=style)
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
