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


def test_ratio_output_sizes_are_exact() -> None:
    assert (geometry.SQUARE.width, geometry.SQUARE.height) == (1080, 1080)
    assert (geometry.PORTRAIT.width, geometry.PORTRAIT.height) == (1080, 1350)
    assert (geometry.LANDSCAPE.width, geometry.LANDSCAPE.height) == (1080, 566)


def test_ratios_are_registered_by_name() -> None:
    assert set(geometry.RATIOS) == {"1:1", "4:5", "1.91:1"}
    assert geometry.RATIOS["4:5"] is geometry.PORTRAIT
    assert geometry.DEFAULT_RATIO is geometry.PORTRAIT


def test_typical_panorama_counts_match_real_samples() -> None:
    # 2.40:1 is the most common aspect across the user's real scans.
    width, height = 7205, 2997
    assert geometry.section_count(width, height, geometry.LANDSCAPE) == 2
    assert geometry.section_count(width, height, geometry.SQUARE) == 2
    assert geometry.section_count(width, height, geometry.PORTRAIT) == 3


def test_large_format_panorama_counts_match_real_samples() -> None:
    # 3.02:1, the two 617 scans.
    width, height = 19921, 6607
    assert geometry.section_count(width, height, geometry.LANDSCAPE) == 2
    assert geometry.section_count(width, height, geometry.SQUARE) == 3
    assert geometry.section_count(width, height, geometry.PORTRAIT) == 4


def test_count_is_floored_at_two() -> None:
    # Tiling alone wants 1 here; the floor is what makes the frames a zoom
    # rather than a restatement of the whole-panorama frame.
    assert geometry.section_count(2400, 1000, geometry.LANDSCAPE) == 2


def test_count_floors_at_two_even_when_narrower_than_one_tile() -> None:
    assert geometry.section_count(500, 1000, geometry.PORTRAIT) == 2


def test_count_rounds_half_up_not_bankers() -> None:
    # tile = 1000 * 1.0 = 1000; 2500/1000 = 2.5 exactly.
    # Python's round() would give 2 (banker's rounding); we want 3.
    assert geometry.section_count(2500, 1000, geometry.SQUARE) == 3
