"""Tests for the preview widget and titles shared by both GUI tabs."""

import tkinter
from pathlib import Path

from auto_border_pano import gui, pipeline


def test_preview_titles_track_the_frame_count() -> None:
    """Frame numbers run 1..N+1 across the whole strip, and only the first
    frame holds the whole panorama.
    """
    assert gui.preview_titles(2) == [
        "FRAME 1 · WHOLE PANORAMA",
        "FRAME 2 · DETAIL",
        "FRAME 3 · DETAIL",
    ]
    assert gui.preview_titles(4) == [
        "FRAME 1 · WHOLE PANORAMA",
        "FRAME 2 · DETAIL",
        "FRAME 3 · DETAIL",
        "FRAME 4 · DETAIL",
        "FRAME 5 · DETAIL",
    ]


def test_preview_titles_match_output_paths_length() -> None:
    for count in (2, 3, 4, 5):
        assert len(gui.preview_titles(count)) == len(pipeline.output_paths("/tmp/x", count))


def test_preview_panes_show_images_displays_a_pil_image_directly(tk_root: tkinter.Tk) -> None:
    """ComposeTab._finish is the only production caller of ``show_images``;
    give it a direct test too so the method is covered without depending on
    the full compose pipeline.
    """
    from PIL import Image

    from auto_border_pano.gui.preview import PreviewPanes

    panes = PreviewPanes(tk_root, "Composite")
    panes.rebuild(["Composite"])
    image = Image.new("RGB", (10, 10), color="red")

    panes.show_images([image])


def test_preview_panes_empty_and_unreadable_states(tk_root: tkinter.Tk, tmp_path: Path) -> None:
    """A pane with no file says the strip is empty; a pane whose file cannot
    be decoded says UNREADABLE and keeps the reason for the caller.
    """
    from auto_border_pano.gui.preview import PreviewPanes

    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"not a jpeg")

    panes = PreviewPanes(tk_root, "Strip")
    panes.rebuild(["one", "two"])

    assert panes.labels[0].cget("text") == "NOTHING ON THE STRIP YET"

    panes.show_paths([tmp_path / "missing.jpg", broken])

    assert panes.labels[0].cget("text") == "NOTHING ON THE STRIP YET"
    assert panes.labels[1].cget("text") == "UNREADABLE"
    assert panes.errors and panes.errors[0].startswith("broken.jpg: ")
