"""Render a solved layout into a single image.

Like geometry.py this works in PIL images and never touches the
filesystem. The layout has already decided every rectangle; this module
only scales and pastes.
"""

import math
from collections.abc import Sequence

from PIL import Image

from auto_border_pano.geometry import BACKGROUND, AspectRatio
from auto_border_pano.layout import Layout

# A box comes from the image's own aspect ratio, so the two should agree to
# within integer rounding. More than this means the solver is wrong, and
# rendering anyway would silently stretch the photograph.
ASPECT_TOLERANCE_PX = 2


def render(images: Sequence[Image.Image], solved: Layout, ratio: AspectRatio) -> Image.Image:
    """Scale each image into its box and paste onto a white canvas."""
    if len(images) != len(solved.boxes):
        raise ValueError(f"layout has {len(solved.boxes)} boxes for {len(images)} images")

    canvas = Image.new("RGB", (ratio.width, ratio.height), BACKGROUND)
    for image, box in zip(images, solved.boxes, strict=True):
        expected = math.floor(box.height * (image.width / image.height) + 0.5)
        if abs(box.width - expected) > ASPECT_TOLERANCE_PX:
            raise ValueError(
                f"box aspect {box.width}x{box.height} does not match image "
                f"{image.width}x{image.height}; refusing to distort it"
            )
        panel = image.resize((box.width, box.height), Image.Resampling.LANCZOS)
        canvas.paste(panel, (box.x, box.y))
    return canvas
