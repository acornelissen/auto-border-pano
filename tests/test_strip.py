"""Tests for the Qt contact strip.

The strip is the signature element, so these are about the promises the
design plan makes rather than about pixels: that the empty state exists
without being asked for, that a caption cannot reach its neighbour, that
the images stay on screen, and that a frame is a frame rather than a panel
filling the column.

They run headless under `QT_QPA_PLATFORM=offscreen`; `qtbot` supplies the
`QApplication`.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import QRect
from PySide6.QtGui import QFontMetrics
from pytestqt.qtbot import QtBot

from maskingframe import pipeline
from maskingframe.gui import strip, theme


@pytest.fixture
def written_frame(tmp_path: Path) -> Path:
    path = tmp_path / "frame.jpg"
    Image.new("RGB", (400, 500), "white").save(path)
    return path


def _built(qtbot: QtBot, frames: int = strip.DEFAULT_FRAME_COUNT) -> strip.ContactStrip:
    widget = strip.ContactStrip(frames=frames)
    qtbot.addWidget(widget)
    return widget


def test_the_empty_state_exists_at_construction_with_no_call(qtbot: QtBot) -> None:
    """The whole point of the widget. The old preview built its container
    and never populated it, so the largest element in the window held zero
    pixels until the first successful run."""
    built = _built(qtbot)

    assert built.frame_count == strip.DEFAULT_FRAME_COUNT
    assert built.exposed == 0
    assert all(built.pixmap_at(index) is None for index in range(built.frame_count))
    # It draws without needing to be told anything.
    built.resize(900, 400)
    built.grab()


def test_the_strip_ends_where_the_film_ends(qtbot: QtBot) -> None:
    """Its background must not run to the full column width: a pale tail
    beyond the last frame reads as an unfinished panel, not a strip."""
    built = _built(qtbot, frames=2)
    built.resize(1400, 400)

    assert built.span < 1400
    assert built.span == 2 * strip.EDGE + 2 * (built.frame_size + strip.GUTTER) - strip.GUTTER


def test_the_frame_count_follows_the_titles(qtbot: QtBot) -> None:
    built = _built(qtbot)

    built.set_frames(["frame 1 . whole panorama", "frame 2 . detail", "frame 3 . detail"])

    assert built.frame_count == 3
    assert built.caption_at(0).startswith("FRAME 1")


def test_a_long_caption_is_elided_to_its_own_frame(qtbot: QtBot) -> None:
    """Unelided, frame 1's caption ran straight through frame 2's:
    "FRAME 1 . WHOLE PANORAM|RAME 2 . DETAIL"."""
    long_title = "frame 1 . the whole panorama end to end with nothing cropped away"
    built = _built(qtbot)
    built.set_frames([long_title, "frame 2 . detail"])
    built.resize(700, 400)

    drawn = [built.caption_at(index) for index in range(built.frame_count)]
    measure = QFontMetrics(theme.stencil_font(10, tracking=1.6))

    assert len(drawn[0]) < len(long_title.upper())
    assert drawn[0].startswith("FRAME 1")
    # No caption can reach its neighbour's frame, whatever the string was.
    for text in drawn:
        assert measure.horizontalAdvance(text) <= built.frame_size


def test_frames_size_from_the_available_width_not_a_constant(qtbot: QtBot) -> None:
    built = _built(qtbot)
    built.set_frames(["a", "b", "c", "d"])

    built.resize(600, 400)
    narrow = built.frame_size
    built.resize(1400, 400)
    wide = built.frame_size

    assert strip.MIN_FRAME_PX <= narrow < wide


def test_a_single_frame_fills_the_space_it_is_given(qtbot: QtBot) -> None:
    """The strip fills its half of the window now: a preview you have to
    squint at is not doing its job. It is still bounded by BOTH dimensions,
    so a lone frame in a tall narrow column cannot become a square taller
    than the column."""
    built = _built(qtbot)
    built.set_frames(["diptych"])

    built.resize(560, 1200)

    assert built.frame_size == 560 - 2 * strip.EDGE
    assert built.frame_size < 1200

    # Given more room it takes more, with no constant ceiling in the way.
    built.resize(560, 900)
    taller = built.frame_size
    built.resize(560, 300)
    assert built.frame_size < taller
    assert built.extent <= 300, "the sheet drew past the bottom of its cell"


def test_a_short_cell_bounds_the_frame_by_height_too(qtbot: QtBot) -> None:
    """A wide short cell must bind on height, or the sheet draws past its
    own bottom edge."""
    built = _built(qtbot)
    built.set_frames(["a"])

    built.resize(1200, 160)

    assert built.frame_size < 1200 - 2 * strip.EDGE
    assert built.extent <= 160


def test_the_strip_never_collapses_below_a_legible_frame(qtbot: QtBot) -> None:
    built = _built(qtbot)
    built.set_frames([f"frame {index}" for index in range(12)])

    built.resize(400, 400)

    assert built.frame_size == strip.MIN_FRAME_PX


def test_the_images_survive_and_the_widget_holds_a_pixmap(
    qtbot: QtBot, written_frame: Path
) -> None:
    built = _built(qtbot)
    built.set_frames(["frame 1 . whole panorama"])
    built.resize(900, 400)

    built.show_paths([written_frame])

    thumbnail = built.pixmap_at(0)
    assert thumbnail is not None
    assert not thumbnail.isNull()
    assert max(thumbnail.width(), thumbnail.height()) == built.frame_size
    built.grab()


def test_show_images_draws_a_pil_image_directly(qtbot: QtBot) -> None:
    built = _built(qtbot)
    built.set_frames(["a", "b"])
    built.resize(900, 400)

    built.show_images([Image.new("RGB", (60, 40), "red"), Image.new("RGB", (60, 40), "blue")])

    assert built.exposed == 2


def test_a_resize_rescales_from_the_bounded_copy(qtbot: QtBot, written_frame: Path) -> None:
    """A source can be 132MP. It is bounded once on the way in, and every
    later size comes off that copy."""
    built = _built(qtbot)
    built.set_frames(["a"])
    built.resize(400, 400)
    built.show_paths([written_frame])
    small = built.pixmap_at(0)
    assert small is not None
    small_height = small.height()

    built.resize(400, 200)

    grown = built.pixmap_at(0)
    assert grown is not None
    assert grown.height() != small_height


def test_an_unreadable_file_keeps_its_reason_for_the_status_line(
    qtbot: QtBot, tmp_path: Path
) -> None:
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"not a jpeg")
    built = _built(qtbot)
    built.set_frames(["frame 1 . whole panorama"])
    built.resize(900, 400)

    built.show_paths([broken])

    assert built.pixmap_at(0) is None
    assert built.is_unreadable(0)
    assert len(built.errors) == 1
    assert "broken.jpg" in built.errors[0]
    built.grab()


def test_a_missing_file_is_unreadable_rather_than_silently_blank(
    qtbot: QtBot, tmp_path: Path
) -> None:
    built = _built(qtbot)
    built.set_frames(["a"])

    built.show_paths([tmp_path / "never-written.jpg"])

    assert built.is_unreadable(0)
    assert built.errors


def test_errors_are_cleared_between_runs(qtbot: QtBot, tmp_path: Path) -> None:
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"not a jpeg")
    built = _built(qtbot)
    built.set_frames(["a"])
    built.show_paths([broken])

    built.set_frames(["a"])

    assert built.errors == []
    assert not built.is_unreadable(0)


def test_frames_are_exposed_one_at_a_time_as_they_are_written(
    qtbot: QtBot, written_frame: Path
) -> None:
    """Progress is the strip filling in, not a bar."""
    built = _built(qtbot)
    built.set_frames(["a", "b", "c"])
    built.resize(900, 400)

    built.mark_written(0, written_frame)
    assert built.exposed == 1
    assert built.pixmap_at(1) is None

    built.mark_written(1, written_frame)
    assert built.exposed == 2
    assert built.pixmap_at(2) is None


def test_an_out_of_range_frame_is_ignored_rather_than_raising(
    qtbot: QtBot, written_frame: Path
) -> None:
    built = _built(qtbot)
    built.set_frames(["a"])

    built.mark_written(4, written_frame)
    built.mark_unreadable(4, "nope")

    assert built.exposed == 0
    assert built.errors == []


def test_the_sheet_wraps_to_use_the_height_it_is_given(qtbot: QtBot) -> None:
    """A contact sheet wraps, and that is what lets the frames actually fill
    the space. Held to one row, the width alone decides how big a frame can
    be, so a tall window just left empty table underneath -- the strip
    filled its cell while painting a thin band at the top of it.
    """
    built = _built(qtbot)
    built.set_frames([f"frame {index}" for index in range(6)])

    built.resize(900, 260)
    flat = built.frame_size
    assert built.columns == 6, "a short cell should keep them on one row"

    built.resize(900, 900)

    assert built.columns < 6, "a tall cell should wrap them"
    assert built.rows > 1
    assert built.frame_size > flat, "wrapping is pointless if frames stay small"
    # And it still fits inside the space it was given.
    assert built.extent <= 900
    assert built.span <= 900


def test_a_wrapped_sheet_still_numbers_every_frame_in_order(qtbot: QtBot) -> None:
    """The numbering is the point: frame 1 is the whole panorama and 2..N
    are its details in order. Wrapping must not renumber them."""
    built = _built(qtbot)
    built.set_frames([f"frame {index}" for index in range(6)])
    built.resize(900, 900)

    assert built.rows > 1
    assert [built.caption_at(index) for index in range(6)] == [
        f"FRAME {index}" for index in range(6)
    ]


# --- the live border preview -------------------------------------------------


def test_the_frame_inside_an_aperture_is_the_target_ratio(qtbot: QtBot) -> None:
    """An aperture is square and an output frame is not, so with nothing
    loaded the frame has to be derived from the ratio rather than assumed."""
    tall = strip.frame_rect(0, 0, 100, 4 / 5)
    assert (tall.x(), tall.y(), tall.width(), tall.height()) == (10, 0, 80, 100)

    wide = strip.frame_rect(0, 0, 100, 2.0)
    assert (wide.x(), wide.y(), wide.width(), wide.height()) == (0, 25, 100, 50)

    square = strip.frame_rect(5, 7, 100, 1.0)
    assert (square.x(), square.y(), square.width(), square.height()) == (5, 7, 100, 100)


def test_the_border_is_a_percent_of_the_frames_short_side(qtbot: QtBot) -> None:
    """Not of the aperture: the frame is what gets printed."""
    bands = strip.border_bands(QRect(10, 0, 80, 100), 0.1)

    assert [(b.x(), b.y(), b.width(), b.height()) for b in bands] == [
        (10, 0, 80, 8),
        (10, 92, 80, 8),
        (10, 8, 8, 84),
        (82, 8, 8, 84),
    ]


def test_a_zero_border_draws_nothing_at_all(qtbot: QtBot) -> None:
    """Not a hairline. No border means no border."""
    assert strip.border_bands(QRect(0, 0, 200, 200), 0.0) == []
    # Nor when a nonzero fraction rounds away to nothing on a tiny frame.
    assert strip.border_bands(QRect(0, 0, 4, 4), 0.05) == []


def test_the_border_covers_only_frame_one_until_the_detail_frames_join_it(
    qtbot: QtBot,
) -> None:
    """The Split tab borders frame 1 always and the details only on
    request, so the drawing must say the same thing."""
    built = _built(qtbot, frames=3)
    built.resize(900, 400)

    built.set_border_preview(
        strip.BorderPreview(aspect=0.8, border=0.1, colour="#ff0000", first_frame_only=True)
    )
    assert built.border_rects(0)
    assert built.border_rects(1) == []
    assert built.border_rects(2) == []

    built.set_border_preview(
        strip.BorderPreview(aspect=0.8, border=0.1, colour="#ff0000", first_frame_only=False)
    )
    assert built.border_rects(1)
    assert built.border_rects(2)


def test_no_preview_means_no_overlay(qtbot: QtBot) -> None:
    """The widget's original behaviour is still reachable."""
    built = _built(qtbot, frames=2)
    built.resize(900, 400)

    assert built.border_preview is None
    assert built.border_rects(0) == []


def test_a_loaded_thumbnails_own_rectangle_is_the_frame(qtbot: QtBot, written_frame: Path) -> None:
    """A thumbnail is already scaled to the output ratio and centred, so its
    own rectangle is the frame -- no second guess at the shape."""
    built = _built(qtbot, frames=1)
    built.resize(600, 500)
    built.show_paths([written_frame])
    built.set_border_preview(strip.BorderPreview(aspect=4 / 5, border=0.1, colour="#ff0000"))

    thumbnail = built.pixmap_at(0)
    assert thumbnail is not None
    frame = built.frame_rect_at(0)
    assert (frame.width(), frame.height()) == (thumbnail.width(), thumbnail.height())


def test_a_rendered_frame_carries_no_overlay(qtbot: QtBot, written_frame: Path) -> None:
    """A render already has the border in it. Drawing the overlay on top
    would lay a second border over the first."""
    built = _built(qtbot, frames=2)
    built.resize(900, 500)
    built.show_paths([written_frame])
    built.set_border_preview(strip.BorderPreview(aspect=4 / 5, border=0.1, colour="#ff0000"))

    assert built.pixmap_at(0) is not None
    assert built.border_rects(0) == []
    # The frame beside it holds nothing, so it still gets the overlay.
    assert built.pixmap_at(1) is None
    assert built.border_rects(1)


def test_clearing_the_images_keeps_the_frames_and_reports_what_went(
    qtbot: QtBot, written_frame: Path
) -> None:
    """Dropping a stale render must not disturb the run it belongs to: the
    count, the titles and the numbering all stay."""
    built = _built(qtbot, frames=3)
    built.resize(900, 500)
    built.set_frames(["frame 1 . whole", "frame 2 . detail", "frame 3 . detail"])
    built.show_paths([written_frame, written_frame])
    built.mark_unreadable(2, "frame.jpg: broken")

    assert built.clear_images() is True

    assert built.frame_count == 3
    assert built.exposed == 0
    assert built.errors == []
    assert not built.is_unreadable(2)
    assert built.caption_at(0) == "FRAME 1 . WHOLE"
    assert all(built.pixmap_at(index) is None for index in range(3))
    # Nothing left to drop, and it says so, so a caller can stay quiet.
    assert built.clear_images() is False


def test_clearing_the_images_brings_the_overlay_back(qtbot: QtBot, written_frame: Path) -> None:
    built = _built(qtbot, frames=1)
    built.resize(600, 500)
    built.set_border_preview(strip.BorderPreview(aspect=4 / 5, border=0.1, colour="#ff0000"))
    built.show_paths([written_frame])
    assert built.border_rects(0) == []

    built.clear_images()

    assert built.border_rects(0)


def test_the_border_is_painted_solid_in_its_own_colour(qtbot: QtBot) -> None:
    """Solid, at full colour: the point is to see the finished frame, not a
    diagram of it. Sampled off a real render rather than trusted."""
    built = _built(qtbot, frames=1)
    built.resize(400, 400)
    built.set_border_preview(strip.BorderPreview(aspect=1.0, border=0.2, colour="#ff0000"))

    image = built.grab().toImage()
    corner = built.border_rects(0)[0]
    sampled = image.pixelColor(corner.x() + 2, corner.y() + 2)
    assert (sampled.red(), sampled.green(), sampled.blue()) == (255, 0, 0)


def test_the_gaps_are_drawn_in_the_gap_colour(qtbot: QtBot) -> None:
    """On a composite the gaps between panels are as much of the result as
    the outer border, and they are a second colour."""
    built = _built(qtbot, frames=1)
    built.resize(400, 400)
    built.set_border_preview(
        strip.BorderPreview(
            aspect=1.0,
            border=0.1,
            colour="#ff0000",
            gaps=(strip.Rect(0.45, 0.1, 0.1, 0.8),),
            gap_colour="#0000ff",
        )
    )

    frame = built.frame_rect_at(0)
    middle = strip.scaled_rect(frame, strip.Rect(0.45, 0.1, 0.1, 0.8))
    image = built.grab().toImage()
    sampled = image.pixelColor(middle.x() + 2, middle.y() + middle.height() // 2)
    assert (sampled.red(), sampled.green(), sampled.blue()) == (0, 0, 255)


def test_a_rendered_composite_shows_its_border_exactly_once(qtbot: QtBot) -> None:
    """The flaw this rule exists for, measured rather than argued.

    `compose_preview` renders the border into the image, so a strip that
    overlaid one as well would show a band twice as thick as the setting.
    A wide source above a tall one at 4:5 arranges into a block that meets
    the top of the frame, so a scan down the middle crosses the border and
    nothing else before reaching the photograph. That run is counted in the
    render and again on screen, and the two must agree once the on-screen
    run is put back into the render's scale.

    The overlay is deliberately set twice as thick as the render's own
    border, because at matching settings the two land on exactly the same
    pixels and a doubled draw cannot be told from a single one. Set apart,
    a second draw shows up as a run twice as long. Scanning across would
    prove nothing: a composite centres its block, and the slack either side
    is border-coloured too, so the run at the left edge is legitimately
    wider than the setting.
    """
    fixtures = Path(__file__).parent / "fixtures"
    ratio = pipeline.RATIOS["4:5"]
    style = pipeline.FrameStyle(border_percent=10.0, border_colour="#ff00ff")
    image, _name = pipeline.compose_preview(
        [fixtures / "compose_wide.jpg", fixtures / "compose_tall.jpg"], ratio, style
    )

    built = _built(qtbot, frames=1)
    built.resize(600, 700)
    built.show_images([image])
    built.set_border_preview(
        strip.BorderPreview(aspect=ratio.width / ratio.height, border=0.2, colour="#ff00ff")
    )

    def run_of_magenta(sample: Callable[[int], tuple[int, int, int]], limit: int) -> int:
        length = 0
        while length < limit:
            red, green, blue = sample(length)
            if not (red > 200 and green < 80 and blue > 200):
                return length
            length += 1
        return length

    rendered = image.convert("RGB")
    middle = rendered.width // 2

    def down_the_middle(y: int) -> tuple[int, int, int]:
        pixel = rendered.getpixel((middle, y))
        assert isinstance(pixel, tuple)
        red, green, blue = pixel[:3]
        return red, green, blue

    baseline = run_of_magenta(down_the_middle, rendered.height)
    # A tenth of the short side, as the setting says, so the yardstick is
    # the rule itself and not just a second guess at it.
    assert baseline == pytest.approx(0.1 * min(rendered.size), abs=2)

    frame = built.frame_rect_at(0)
    grabbed = built.grab().toImage()
    column = frame.x() + frame.width() // 2

    def on_screen(y: int) -> tuple[int, int, int]:
        pixel = grabbed.pixelColor(column, frame.y() + y)
        return pixel.red(), pixel.green(), pixel.blue()

    shown = run_of_magenta(on_screen, frame.height())
    scale = rendered.height / frame.height()

    assert shown * scale == pytest.approx(
        baseline, abs=3 * scale
    ), f"the border ran {shown * scale:.0f}px of the render, which holds {baseline}px"


def test_the_composite_overlay_matches_what_a_render_actually_produces(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """The exactness this overlay exists for, measured against a real render.

    `layout.evaluate` fits the panel block inside the frame's inset box and
    then centres it, so on whichever axis the block does not fill the box
    there is leftover slack -- and `compose.render` paints that slack in the
    border colour too. A nominal band of `border_percent` around the edge
    therefore understates the finished border, sometimes by more than twice.

    So this compares the overlay against the render rather than against a
    restatement of the formula: render a composite, drive the strip's
    overlay for the same sources and style with nothing loaded, and walk a
    grid across the frame asserting the two agree at every point about
    whether that point is border. Points near a panel or gap edge are
    skipped -- the two are drawn at different scales, so a boundary lands
    within a pixel or so either way and proves nothing.

    The sources are flat rather than the photographic fixtures, and the two
    shapes are the fixtures' own (600x250 beside 400x400, the pair the
    measurement in the plan was taken from). A photograph contains a few
    pixels of any colour you name, including the border's, so "is this
    point border?" has to be a question about the composition rather than
    about the picture.
    """
    ratio = pipeline.RATIOS["4:5"]
    style = pipeline.FrameStyle(
        border_percent=6.0,
        border_colour="#ff00ff",
        gutter_percent=4.0,
        gutter_colour="#00ff00",
    )
    sources = []
    for name, size in (("wide", (600, 250)), ("square", (400, 400))):
        path = tmp_path / f"{name}.png"
        Image.new("RGB", size, (30, 30, 30)).save(path)
        sources.append(path)
    rendered, _name = pipeline.compose_preview(sources, ratio, style)
    rendered = rendered.convert("RGB")

    aspects = []
    for path in sources:
        with Image.open(path) as opened:
            aspects.append(opened.width / opened.height)
    solved = pipeline.composite_rects(aspects, ratio, style)

    built = _built(qtbot, frames=1)
    built.resize(600, 700)
    built.set_border_preview(
        strip.BorderPreview(
            aspect=ratio.width / ratio.height,
            border=style.border_percent / 100,
            colour=style.border_colour,
            gaps=tuple(strip.Rect(*gap) for gap in solved.gaps),
            gap_colour=style.gutter_colour,
            panels=tuple(strip.Rect(*panel) for panel in solved.panels),
        )
    )

    frame = built.frame_rect_at(0)
    grabbed = built.grab().toImage()

    def is_border(red: int, green: int, blue: int) -> bool:
        return (red, green, blue) == (255, 0, 255)

    def near_an_edge(u: float, v: float) -> bool:
        """Within a pixel or so of any panel or gap boundary, at strip scale."""
        margin = 3 / min(frame.width(), frame.height())
        for x, y, width, height in solved.panels + solved.gaps:
            for value, low, high in ((u, x, x + width), (v, y, y + height)):
                if abs(value - low) < margin or abs(value - high) < margin:
                    return True
        return False

    checked = 0
    for step_u in range(1, 60):
        for step_v in range(1, 60):
            u, v = step_u / 60, step_v / 60
            if near_an_edge(u, v):
                continue
            pixel = rendered.getpixel((int(u * rendered.width), int(v * rendered.height)))
            assert isinstance(pixel, tuple)
            in_render = is_border(*pixel[:3])
            colour = grabbed.pixelColor(
                frame.x() + int(u * frame.width()), frame.y() + int(v * frame.height())
            )
            on_screen = is_border(colour.red(), colour.green(), colour.blue())
            assert on_screen == in_render, (
                f"at ({u:.2f}, {v:.2f}) the render says "
                f"{'border' if in_render else 'panel'} and the overlay says "
                f"{'border' if on_screen else 'panel'}"
            )
            checked += 1

    # Enough of the grid survived the edge margin to make the walk mean
    # something, and enough of it is border to catch a missed axis of slack.
    assert checked > 2000
