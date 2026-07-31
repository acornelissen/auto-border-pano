"""Characterisation tests for the pure geometry transforms.

These lock in current behaviour exactly, including the padding quirk where
the vertical padding constant only influences canvas size and the panorama
ends up vertically centered.
"""

import pytest

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


def test_section_bounds_split_on_integer_division() -> None:
    # 3001 // 3 == 1000, so the final pixel is discarded. Preserved.
    assert geometry.section_bounds(3001, 0) == (0, 1000)
    assert geometry.section_bounds(3001, 1) == (1000, 2000)
    assert geometry.section_bounds(3001, 2) == (2000, 3000)


def test_every_section_is_square_and_1080() -> None:
    panorama = synthetic_panorama(3000, 800)
    for index in range(geometry.SECTION_COUNT):
        assert geometry.make_section(panorama, index).size == (1080, 1080)


def test_section_honours_explicit_size() -> None:
    result = geometry.make_section(synthetic_panorama(3000, 800), 0, size=256)
    assert result.size == (256, 256)


def test_tall_section_scales_on_width() -> None:
    # A section narrower than it is tall takes the else branch: scale to
    # width, then crop vertically. 300 wide / 3 = 100 per section.
    result = geometry.make_section(synthetic_panorama(300, 900), 0)
    assert result.size == (1080, 1080)


def test_section_index_is_validated() -> None:
    with pytest.raises(ValueError):
        geometry.make_section(synthetic_panorama(300, 100), 3)
