"""Tests for the preview widget and titles shared by both GUI tabs."""

from auto_border_pano import gui, pipeline


def test_preview_titles_track_the_frame_count() -> None:
    assert gui.preview_titles(2) == ["Whole", "Detail 1", "Detail 2"]
    assert gui.preview_titles(4) == [
        "Whole",
        "Detail 1",
        "Detail 2",
        "Detail 3",
        "Detail 4",
    ]


def test_preview_titles_match_output_paths_length() -> None:
    for count in (2, 3, 4, 5):
        assert len(gui.preview_titles(count)) == len(pipeline.output_paths("/tmp/x", count))


def test_preview_panes_show_images_displays_a_pil_image_directly() -> None:
    """ComposeTab._finish is the only production caller of ``show_images``;
    give it a direct test too so the method is covered without depending on
    the full compose pipeline.
    """
    import tkinter

    from PIL import Image

    from auto_border_pano.gui.preview import PreviewPanes

    root = tkinter.Tk()
    root.withdraw()
    try:
        panes = PreviewPanes(root, "Composite")
        panes.rebuild(["Composite"])
        image = Image.new("RGB", (10, 10), color="red")

        panes.show_images([image])
    finally:
        root.destroy()
