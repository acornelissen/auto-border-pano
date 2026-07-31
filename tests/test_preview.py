"""Tests for the frame titles both GUI tabs put on the contact strip.

The widget these titles used to feed, `PreviewPanes`, is gone -- stage 4
replaced it with `ContactStrip`, which `tests/test_strip.py` covers. The
titles outlived it, so they keep their tests here.
"""

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
