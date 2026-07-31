"""Tests for the Qt contact strip.

The strip is the signature element, so these are about the promises the
design plan makes rather than about pixels: that the empty state exists
without being asked for, that a caption cannot reach its neighbour, that
the images stay on screen, and that a frame is a frame rather than a panel
filling the column.

They run headless under `QT_QPA_PLATFORM=offscreen`; `qtbot` supplies the
`QApplication`.
"""

from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtGui import QFontMetrics
from pytestqt.qtbot import QtBot

from auto_border_pano.gui import strip, theme


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

    assert strip.MIN_FRAME_PX <= narrow < wide <= strip.MAX_FRAME_PX


def test_a_single_frame_is_a_frame_not_a_column_sized_square(qtbot: QtBot) -> None:
    """Compose builds the strip with one frame in a tall narrow column.
    Sized from the width alone that produced one enormous square."""
    built = _built(qtbot)
    built.set_frames(["diptych"])

    built.resize(560, 1200)

    assert built.frame_size <= strip.MAX_FRAME_PX
    assert built.frame_size < 560 - 2 * strip.EDGE
    # And it asks for its own height, not the column's.
    assert built.sizeHint().height() == built.frame_size + strip.CHROME_PX
    assert built.sizeHint().height() < 1200 / 2


def test_a_short_cell_bounds_the_frame_by_height_too(qtbot: QtBot) -> None:
    built = _built(qtbot)
    built.set_frames(["a"])

    built.resize(1200, 160)

    assert built.frame_size == 160 - strip.CHROME_PX


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
