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
