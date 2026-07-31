"""Characterisation tests for the pure geometry transforms.

These lock in current behaviour exactly, including the padding quirk where
the vertical padding constant only influences canvas size and the panorama
ends up vertically centered.
"""

from auto_border_pano import geometry
from tests.conftest import synthetic_panorama


def test_canvas_is_width_plus_two_side_paddings_for_wide_panorama() -> None:
    assert geometry.padded_square_size(3000, 800) == 3200


def test_canvas_uses_height_term_when_image_is_tall() -> None:
    # height + 20 exceeds width + 200 only when the image is nearly square
    # or taller than it is wide.
    assert geometry.padded_square_size(100, 800) == 820


def test_padded_square_is_square_and_correctly_sized() -> None:
    result = geometry.make_padded_square(synthetic_panorama(3000, 800))
    assert result.size == (3200, 3200)


def test_padded_square_centers_the_panorama() -> None:
    # The panorama is centered, so the top gap is (3200 - 800) // 2 = 1200,
    # NOT the 10px VERTICAL_PADDING. This is the documented quirk.
    result = geometry.make_padded_square(synthetic_panorama(3000, 800))
    assert result.getpixel((1600, 1199)) == (255, 255, 255)
    assert result.getpixel((1600, 1201)) != (255, 255, 255)


def test_padded_square_background_is_white() -> None:
    result = geometry.make_padded_square(synthetic_panorama(3000, 800))
    assert result.getpixel((0, 0)) == (255, 255, 255)
