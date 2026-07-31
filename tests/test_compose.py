"""Tests for composite rendering."""

import pytest
from PIL import Image

from auto_border_pano import compose, geometry, layout

PADDING = geometry.SIDE_PADDING


def _image(width: int, height: int, colour: tuple[int, int, int]) -> Image.Image:
    return Image.new("RGB", (width, height), colour)


def test_composite_is_exactly_the_target_size() -> None:
    images = [_image(900, 300, (255, 0, 0)), _image(900, 300, (0, 255, 0))]
    aspects = [im.width / im.height for im in images]
    for ratio in geometry.RATIOS.values():
        solved = layout.solve(aspects, ratio, PADDING)
        result = compose.render(images, solved, ratio)
        assert result.size == (ratio.width, ratio.height), ratio.name


def test_background_is_white() -> None:
    images = [_image(900, 300, (255, 0, 0)), _image(900, 300, (0, 255, 0))]
    aspects = [im.width / im.height for im in images]
    solved = layout.solve(aspects, geometry.PORTRAIT, PADDING)
    result = compose.render(images, solved, geometry.PORTRAIT)
    assert result.getpixel((0, 0)) == (255, 255, 255)


def test_every_panel_lands_where_the_layout_said() -> None:
    # Distinct flat colours make each panel identifiable by pixel probe.
    images = [_image(900, 300, (255, 0, 0)), _image(300, 900, (0, 0, 255))]
    aspects = [im.width / im.height for im in images]
    solved = layout.solve(aspects, geometry.SQUARE, PADDING)
    result = compose.render(images, solved, geometry.SQUARE)
    for box, colour in zip(solved.boxes, [(255, 0, 0), (0, 0, 255)], strict=True):
        centre = (box.x + box.width // 2, box.y + box.height // 2)
        assert result.getpixel(centre) == colour, (box, colour)


def test_render_rejects_a_layout_that_would_distort_a_panel() -> None:
    # A box whose aspect disagrees with its image means the solver is
    # broken; rendering must fail loudly rather than stretch the photo.
    images = [_image(900, 300, (255, 0, 0)), _image(900, 300, (0, 255, 0))]
    bad = layout.Layout(
        "bad",
        (layout.Box(100, 100, 400, 400), layout.Box(100, 600, 400, 400)),
        0.5,
    )
    with pytest.raises(ValueError, match="aspect"):
        compose.render(images, bad, geometry.SQUARE)


def test_render_requires_one_box_per_image() -> None:
    images = [_image(900, 300, (255, 0, 0))]
    solved = layout.Layout("bad", (layout.Box(0, 0, 10, 10), layout.Box(20, 0, 10, 10)), 0.5)
    with pytest.raises(ValueError):
        compose.render(images, solved, geometry.SQUARE)


def test_extreme_aspect_ratio_with_small_height() -> None:
    # Regression: extreme aspect ratios with small heights should not cause false rejections.
    # layout._place rounds each dimension independently, so there can be accumulated
    # rounding error; the tolerance must account for this.
    # Example: aspect ~8.21, height ~45 used to fail with 2px tolerance but is valid.
    images = [_image(821, 100, (255, 0, 0)), _image(900, 300, (0, 255, 0))]  # aspect ~8.21
    aspects = [im.width / im.height for im in images]
    solved = layout.solve(aspects, geometry.SQUARE, PADDING)
    # Should not raise ValueError due to aspect mismatch
    result = compose.render(images, solved, geometry.SQUARE)
    assert result.size == (geometry.SQUARE.width, geometry.SQUARE.height)
