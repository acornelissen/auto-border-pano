"""Pure image transforms.

Every function here takes and returns PIL Images. Nothing in this module
opens or writes a file, which is what makes it fast to test.
"""

from PIL import Image

SIDE_PADDING = 100
VERTICAL_PADDING = 10
BACKGROUND = "white"


def padded_square_size(width: int, height: int) -> int:
    """Return the edge length of the square canvas for a panorama.

    Note that for any normal wide panorama the width term wins, so the
    vertical padding never actually applies -- see make_padded_square.
    """
    return max(width + 2 * SIDE_PADDING, height + 2 * VERTICAL_PADDING)


def make_padded_square(image: Image.Image) -> Image.Image:
    """Center a panorama on a white square canvas.

    The panorama is centered rather than offset by VERTICAL_PADDING, so a
    wide panorama gets exactly SIDE_PADDING left and right and a much
    larger leftover gap top and bottom. Preserved deliberately.
    """
    width, height = image.size
    size = padded_square_size(width, height)
    canvas = Image.new("RGB", (size, size), BACKGROUND)
    canvas.paste(image, ((size - width) // 2, (size - height) // 2))
    return canvas


SECTION_SIZE = 1080
SECTION_COUNT = 3


def section_bounds(width: int, index: int) -> tuple[int, int]:
    """Return the horizontal crop bounds of one section.

    Uses integer division, so when the width is not divisible by
    SECTION_COUNT the remaining pixels on the right edge are discarded.
    """
    if not 0 <= index < SECTION_COUNT:
        raise ValueError(f"index must be 0..{SECTION_COUNT - 1}, got {index}")
    section_width = width // SECTION_COUNT
    start = index * section_width
    return start, start + section_width


def make_section(image: Image.Image, index: int, size: int = SECTION_SIZE) -> Image.Image:
    """Crop one section of the panorama and fill a square of `size`.

    Scales on whichever axis keeps the square fully covered, then
    center-crops the overflow.
    """
    width, height = image.size
    start, end = section_bounds(width, index)
    crop = image.crop((start, 0, end, height))
    crop_width, crop_height = crop.size

    if crop_width > crop_height:
        scale = size / crop_height
        resized = crop.resize((int(crop_width * scale), size), Image.Resampling.LANCZOS)
        offset = (resized.width - size) // 2
        return resized.crop((offset, 0, offset + size, size))

    scale = size / crop_width
    resized = crop.resize((size, int(crop_height * scale)), Image.Resampling.LANCZOS)
    offset = (resized.height - size) // 2
    return resized.crop((0, offset, size, offset + size))
