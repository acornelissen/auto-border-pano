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


def render(images: Sequence[Image.Image], solved: Layout, ratio: AspectRatio) -> Image.Image:
    """Scale each image into its box and paste onto a white canvas."""
    if len(images) != len(solved.boxes):
        raise ValueError(f"layout has {len(solved.boxes)} boxes for {len(images)} images")

    canvas = Image.new("RGB", (ratio.width, ratio.height), BACKGROUND)
    for image, box in zip(images, solved.boxes, strict=True):
        # layout._place rounds width and height independently. For a given box.height,
        # the pre-rounded height could have been anywhere in [height-0.5, height+0.5).
        # This means box.width could legitimately be anywhere in the range of widths
        # that result from those heights, plus ±1px slack for rounding on width itself.
        aspect = image.width / image.height
        min_width = math.floor((box.height - 0.5) * aspect + 0.5) - 1
        max_width = math.floor((box.height + 0.5) * aspect + 0.5) + 1
        if not (min_width <= box.width <= max_width):
            raise ValueError(
                f"box aspect {box.width}x{box.height} does not match image "
                f"{image.width}x{image.height}; refusing to distort it"
            )
        panel = image.resize((box.width, box.height), Image.Resampling.LANCZOS)
        canvas.paste(panel, (box.x, box.y))
    return canvas
