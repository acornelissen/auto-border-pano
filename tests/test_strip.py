"""Tests for the contact strip.

The strip is the stage's signature element, so these tests are about the
promises the design plan makes rather than about pixels: that the empty
state exists without being asked for, that rebuilding does not leak, that
the images stay on screen, and that frames size from the window.
"""

import gc
import tkinter
from pathlib import Path

import pytest
from PIL import Image

from auto_border_pano.gui import strip, theme


@pytest.fixture
def written_frame(tmp_path: Path) -> Path:
    path = tmp_path / "frame.jpg"
    Image.new("RGB", (400, 500), "white").save(path)
    return path


def test_the_empty_state_is_drawn_at_construction_with_no_call(tk_root: tkinter.Tk) -> None:
    """The whole point of the stage. The old preview built its container and
    never populated it, so the largest element in the window held zero
    pixels until the first successful run."""
    built = strip.ContactStrip(tk_root)

    assert built.canvas.find_withtag("rebate")
    assert len(built.canvas.find_withtag("number")) == built.frame_count
    captions = built.canvas.find_withtag("caption")
    assert [built.canvas.itemcget(item, "text") for item in captions] == [strip.EMPTY_CAPTION]  # type: ignore[no-untyped-call]


def test_the_empty_caption_appears_once_not_once_per_frame(tk_root: tkinter.Tk) -> None:
    built = strip.ContactStrip(tk_root)

    built.set_frames(["frame 1 . whole panorama", "frame 2 . detail", "frame 3 . detail"])

    assert built.frame_count == 3
    assert len(built.canvas.find_withtag("caption")) == 1


def test_the_strip_is_film_base_black_on_the_light_table(tk_root: tkinter.Tk) -> None:
    built = strip.ContactStrip(tk_root)

    rebate = built.canvas.find_withtag("rebate")[0]

    assert built.canvas.cget("background") == theme.LIGHTBOX
    assert built.canvas.itemcget(rebate, "fill") == theme.REBATE  # type: ignore[no-untyped-call]


def test_stencils_are_stamped_in_caps_like_a_lab_would(tk_root: tkinter.Tk) -> None:
    built = strip.ContactStrip(tk_root)

    built.set_frames(["frame 1 . whole panorama"])

    stencils = built.canvas.find_withtag("stencil")
    assert [built.canvas.itemcget(item, "text") for item in stencils] == [  # type: ignore[no-untyped-call]
        "FRAME 1 . WHOLE PANORAMA"
    ]


def test_rebuilding_at_a_new_frame_count_does_not_accumulate_items(
    tk_root: tkinter.Tk,
) -> None:
    """The count varies with the ratio and the panorama, so this runs on
    every run. Leaving stale items behind would pile them up."""
    built = strip.ContactStrip(tk_root)

    built.set_frames(["a", "b", "c", "d", "e"])
    built.set_frames(["a", "b"])
    after_first = len(built.canvas.find_all())
    for _ in range(5):
        built.set_frames(["a", "b"])

    assert len(built.canvas.find_all()) == after_first
    assert len(built.canvas.find_withtag("number")) == 2


def test_shrinking_the_strip_drops_the_stale_image_references(
    tk_root: tkinter.Tk, written_frame: Path
) -> None:
    built = strip.ContactStrip(tk_root)
    built.set_frames(["a", "b", "c"])
    built.show_paths([written_frame, written_frame, written_frame])

    built.set_frames(["a"])

    assert built.canvas.find_withtag("frame") == ()


def test_images_survive_garbage_collection(tk_root: tkinter.Tk, written_frame: Path) -> None:
    """Tk drops an image the moment its PhotoImage is collected and renders
    a blank in its place. The strip holds its references for exactly that
    reason -- a Canvas needs it as much as a Label does."""
    built = strip.ContactStrip(tk_root)
    built.set_frames(["frame 1 . whole panorama"])

    built.show_paths([written_frame])
    gc.collect()
    tk_root.update_idletasks()

    drawn = built.canvas.find_withtag("frame")
    assert len(drawn) == 1
    name = built.canvas.itemcget(drawn[0], "image")  # type: ignore[no-untyped-call]
    assert name != ""
    # The image is still known to the interpreter, not a collected blank.
    assert int(tk_root.tk.call("image", "width", name)) > 0


def test_show_images_draws_a_pil_image_directly(tk_root: tkinter.Tk) -> None:
    built = strip.ContactStrip(tk_root)
    built.set_frames(["a", "b"])

    built.show_images([Image.new("RGB", (60, 40), "red"), Image.new("RGB", (60, 40), "blue")])

    assert len(built.canvas.find_withtag("frame")) == 2
    assert built.canvas.find_withtag("caption") == ()


def test_an_unreadable_file_keeps_its_reason_for_the_status_line(
    tk_root: tkinter.Tk, tmp_path: Path
) -> None:
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"not a jpeg")
    built = strip.ContactStrip(tk_root)
    built.set_frames(["frame 1 . whole panorama"])

    built.show_paths([broken])

    assert built.canvas.find_withtag("frame") == ()
    unreadable = built.canvas.find_withtag("unreadable")
    assert [built.canvas.itemcget(item, "text") for item in unreadable] == [  # type: ignore[no-untyped-call]
        strip.UNREADABLE_CAPTION
    ]
    assert len(built.errors) == 1
    assert "broken.jpg" in built.errors[0]


def test_a_missing_file_is_unreadable_rather_than_silently_blank(
    tk_root: tkinter.Tk, tmp_path: Path
) -> None:
    built = strip.ContactStrip(tk_root)
    built.set_frames(["a"])

    built.show_paths([tmp_path / "never-written.jpg"])

    assert built.errors


def test_errors_are_cleared_between_runs(tk_root: tkinter.Tk, tmp_path: Path) -> None:
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"not a jpeg")
    built = strip.ContactStrip(tk_root)
    built.set_frames(["a"])
    built.show_paths([broken])

    built.set_frames(["a"])

    assert built.errors == []


def test_frames_are_exposed_one_at_a_time_as_they_are_written(
    tk_root: tkinter.Tk, written_frame: Path
) -> None:
    """Progress is the strip filling in, not a bar."""
    built = strip.ContactStrip(tk_root)
    built.set_frames(["a", "b", "c"])

    built.mark_written(0, written_frame)
    assert len(built.canvas.find_withtag("frame")) == 1
    # One frame exposed means the strip is no longer unexposed.
    assert built.canvas.find_withtag("caption") == ()

    built.mark_written(1, written_frame)
    assert len(built.canvas.find_withtag("frame")) == 2
    assert built.canvas.find_withtag("frame2") == ()


def test_frames_size_from_the_available_width_not_a_constant(tk_root: tkinter.Tk) -> None:
    built = strip.ContactStrip(tk_root)
    built.set_frames(["a", "b", "c", "d"])

    built.set_available_width(600)
    narrow = built.frame_size
    built.set_available_width(1400)
    wide = built.frame_size

    assert strip.MIN_FRAME_PX <= narrow < wide <= strip.MAX_FRAME_PX


def test_a_configure_before_the_first_real_size_does_not_lay_out(
    tk_root: tkinter.Tk,
) -> None:
    """Tk reports width 1 before the geometry manager has a real size. Laying
    out against that would slice the strip into slivers and thrash back."""
    built = strip.ContactStrip(tk_root)
    built.set_frames(["a", "b", "c", "d"])
    built.set_available_width(1400)
    wide = built.frame_size

    built.set_available_width(1)

    assert built.frame_size == wide


def test_the_strip_never_collapses_below_a_legible_frame(tk_root: tkinter.Tk) -> None:
    built = strip.ContactStrip(tk_root)
    built.set_frames([f"frame {index}" for index in range(12)])

    built.set_available_width(400)

    assert built.frame_size == strip.MIN_FRAME_PX


def test_a_resize_rescales_the_thumbnails_it_already_holds(
    tk_root: tkinter.Tk, written_frame: Path
) -> None:
    built = strip.ContactStrip(tk_root)
    built.set_frames(["a"])
    built.set_available_width(400)
    built.show_paths([written_frame])

    built.set_available_width(1200)

    assert len(built.canvas.find_withtag("frame")) == 1
    drawn = built.canvas.find_withtag("frame")[0]
    name = built.canvas.itemcget(drawn, "image")  # type: ignore[no-untyped-call]
    assert int(tk_root.tk.call("image", "height", name)) > strip.MIN_FRAME_PX
