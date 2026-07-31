"""Characterisation tests for the pure geometry transforms.

These lock in current behaviour exactly, including the padding quirk where
the vertical padding constant only influences canvas size and the panorama
ends up vertically centered.
"""

import pytest
from PIL import Image

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


def test_padded_square_pastes_at_side_padding_not_zero() -> None:
    # The panorama must start exactly SIDE_PADDING (100) pixels from the
    # left edge, not at x=0. synthetic_panorama's pixel (0, y) is (0, y%256,
    # y%256), which is never white, so a white pixel just inside the left
    # padding column plus a non-white pixel just past it proves the offset.
    result = geometry.make_padded_square(synthetic_panorama(3000, 800))
    top = (3200 - 800) // 2  # vertical center offset for this panorama
    assert result.getpixel((99, top)) == (255, 255, 255)
    assert result.getpixel((100, top)) == (0, 0, 0)  # source pixel (0, 0)
    # source pixel (2999, 0) = (2999 % 256, 0, 2999 % 256) = (183, 0, 183)
    assert result.getpixel((100 + 2999, top)) == (183, 0, 183)


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


def test_wide_section_center_crop_uses_the_computed_offset_not_zero() -> None:
    # make_section's wide branch scales to height then center-crops the
    # overflow horizontally. Independently reproduce that arithmetic here
    # (not by calling geometry code) so a mutation that hardcodes the crop
    # offset to 0 changes `actual` but not this `expected`.
    panorama = synthetic_panorama(3000, 800)
    crop = panorama.crop((0, 0, 1000, 800))  # section 0's bounds: 3000 // 3 = 1000
    scale = 1080 / 800
    resized = crop.resize((int(1000 * scale), 1080), Image.Resampling.LANCZOS)
    offset = (resized.width - 1080) // 2
    assert offset != 0  # sanity: this test is only meaningful if the true offset is nonzero
    expected_pixel = resized.getpixel((offset + 500, 500))

    actual = geometry.make_section(panorama, 0)

    assert actual.getpixel((500, 500)) == expected_pixel


def test_tall_section_center_crop_uses_the_computed_offset_not_zero() -> None:
    # Mirror of the wide-branch test above, but for the else branch (scale
    # to width, center-crop vertically), which the tall panorama exercises.
    panorama = synthetic_panorama(300, 900)
    crop = panorama.crop((0, 0, 100, 900))  # section 0's bounds: 300 // 3 = 100
    scale = 1080 / 100
    resized = crop.resize((1080, int(900 * scale)), Image.Resampling.LANCZOS)
    offset = (resized.height - 1080) // 2
    assert offset != 0  # sanity: this test is only meaningful if the true offset is nonzero
    expected_pixel = resized.getpixel((500, offset + 500))

    actual = geometry.make_section(panorama, 0)

    assert actual.getpixel((500, 500)) == expected_pixel
