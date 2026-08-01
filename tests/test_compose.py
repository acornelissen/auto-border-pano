"""Tests for composite rendering."""

import pytest
from PIL import Image

from maskingframe import compose, geometry, layout
from maskingframe.geometry import DEFAULT_STYLE, FrameStyle

TWO_TONE = FrameStyle(
    border_percent=9.0,
    border_colour="#000000",
    gutter_percent=4.0,
    gutter_colour="#c9302a",
)


def _image(width: int, height: int, colour: tuple[int, int, int]) -> Image.Image:
    return Image.new("RGB", (width, height), colour)


def test_composite_is_exactly_the_target_size() -> None:
    images = [_image(900, 300, (255, 0, 0)), _image(900, 300, (0, 255, 0))]
    aspects = [im.width / im.height for im in images]
    for ratio in geometry.RATIOS.values():
        solved = layout.solve(aspects, ratio, DEFAULT_STYLE)
        result = compose.render(images, solved, ratio)
        assert result.size == (ratio.width, ratio.height), ratio.name


def test_background_is_white() -> None:
    images = [_image(900, 300, (255, 0, 0)), _image(900, 300, (0, 255, 0))]
    aspects = [im.width / im.height for im in images]
    solved = layout.solve(aspects, geometry.PORTRAIT, DEFAULT_STYLE)
    result = compose.render(images, solved, geometry.PORTRAIT)
    assert result.getpixel((0, 0)) == (255, 255, 255)


def test_every_panel_lands_where_the_layout_said() -> None:
    # Distinct flat colours make each panel identifiable by pixel probe.
    images = [_image(900, 300, (255, 0, 0)), _image(300, 900, (0, 0, 255))]
    aspects = [im.width / im.height for im in images]
    solved = layout.solve(aspects, geometry.SQUARE, DEFAULT_STYLE)
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
        (),
        0.5,
    )
    with pytest.raises(ValueError, match="aspect"):
        compose.render(images, bad, geometry.SQUARE)


def test_render_requires_one_box_per_image() -> None:
    images = [_image(900, 300, (255, 0, 0))]
    solved = layout.Layout("bad", (layout.Box(0, 0, 10, 10), layout.Box(20, 0, 10, 10)), (), 0.5)
    with pytest.raises(ValueError):
        compose.render(images, solved, geometry.SQUARE)


def test_rendered_dark_pixel_count_matches_the_solved_box_areas() -> None:
    # Probing one centre pixel per panel (as above) would still pass if the
    # renderer pasted at the wrong offset or resized a panel to the wrong
    # size, so long as the centre happened to land on the panel's own
    # colour. Render every panel a known dark colour on the white canvas and
    # count dark pixels instead: that total can only match the solver's own
    # box areas if every panel was actually placed and sized correctly.
    dark = (10, 10, 10)
    images = [_image(900, 300, dark), _image(300, 900, dark), _image(600, 600, dark)]
    aspects = [im.width / im.height for im in images]
    for ratio in geometry.RATIOS.values():
        solved = layout.solve(aspects, ratio, DEFAULT_STYLE)
        result = compose.render(images, solved, ratio)

        expected_area = sum(box.width * box.height for box in solved.boxes)
        dark_pixels = sum(
            1
            for y in range(result.height)
            for x in range(result.width)
            if result.getpixel((x, y)) == dark
        )

        assert dark_pixels == expected_area, ratio.name


def test_extreme_aspect_ratio_with_small_height() -> None:
    # Regression: extreme aspect ratios with small heights should not cause false rejections.
    # layout._place rounds each dimension independently, so there can be accumulated
    # rounding error; the tolerance must account for this.
    # Example: aspect ~8.21, height ~45 used to fail with 2px tolerance but is valid.
    images = [_image(821, 100, (255, 0, 0)), _image(900, 300, (0, 255, 0))]  # aspect ~8.21
    aspects = [im.width / im.height for im in images]
    solved = layout.solve(aspects, geometry.SQUARE, DEFAULT_STYLE)
    # Should not raise ValueError due to aspect mismatch
    result = compose.render(images, solved, geometry.SQUARE)
    assert result.size == (geometry.SQUARE.width, geometry.SQUARE.height)


def _rendered(style: FrameStyle) -> tuple[Image.Image, layout.Layout]:
    images = [_image(1500, 1000, (255, 255, 255)), _image(1500, 1000, (255, 255, 255))]
    solved = layout.solve([1.5, 1.5], geometry.PORTRAIT, style)
    return compose.render(images, solved, geometry.PORTRAIT, style), solved


def test_outer_border_takes_the_border_colour() -> None:
    canvas, _solved = _rendered(TWO_TONE)
    assert canvas.getpixel((0, 0)) == (0, 0, 0)
    assert canvas.getpixel((canvas.width - 1, canvas.height - 1)) == (0, 0, 0)


def test_the_strip_between_panels_takes_the_gutter_colour() -> None:
    canvas, solved = _rendered(TWO_TONE)
    gutter = solved.gutters[0]
    centre = (gutter.x + gutter.width // 2, gutter.y + gutter.height // 2)
    assert canvas.getpixel(centre) == (201, 48, 42)


def test_no_border_colour_leaks_between_the_panels() -> None:
    canvas, solved = _rendered(TWO_TONE)
    first, second = solved.boxes
    # Walk the line joining the two panels; every pixel is panel or gutter,
    # never the outer colour.
    if first.x + first.width <= second.x:
        row = first.y + first.height // 2
        span = range(first.x + first.width, second.x)
        pixels = [canvas.getpixel((column, row)) for column in span]
    else:
        column = first.x + first.width // 2
        span = range(first.y + first.height, second.y)
        pixels = [canvas.getpixel((column, row)) for row in span]
    assert pixels
    assert (0, 0, 0) not in pixels


def test_a_zero_gutter_paints_nothing_extra() -> None:
    style = FrameStyle(border_colour="#000000", gutter_percent=0.0, gutter_colour="#c9302a")
    canvas, solved = _rendered(style)
    assert solved.gutters == ()
    colours = canvas.getcolors(maxcolors=1 << 20)
    assert colours is not None
    assert all(colour != (201, 48, 42) for _count, colour in colours)


def test_render_still_refuses_a_mismatched_box() -> None:
    images = [_image(1500, 1000, (255, 255, 255)), _image(1000, 1500, (255, 255, 255))]
    solved = layout.solve([1.5, 1.5], geometry.PORTRAIT, TWO_TONE)
    with pytest.raises(ValueError, match="refusing to distort"):
        compose.render(images, solved, geometry.PORTRAIT, TWO_TONE)
