"""Render a solved layout into a single image.

Like geometry.py this works in PIL images and never touches the
filesystem. The layout has already decided every rectangle; this module
only scales and pastes.
"""

import math
from collections.abc import Sequence

from PIL import Image

from maskingframe.geometry import DEFAULT_STYLE, AspectRatio, FrameStyle
from maskingframe.layout import Layout


def render(
    images: Sequence[Image.Image],
    solved: Layout,
    ratio: AspectRatio,
    style: FrameStyle = DEFAULT_STYLE,
) -> Image.Image:
    """Scale each image into its box and paste onto the styled canvas.

    Three passes, in this order: the whole canvas takes the border colour,
    the separator rectangles take the gutter colour, then the panels land on
    top. Painting the gutters first is what lets them be inflated by a pixel
    without showing -- the panels cover the overlap.
    """
    if len(images) != len(solved.boxes):
        raise ValueError(f"layout has {len(solved.boxes)} boxes for {len(images)} images")

    canvas = Image.new("RGB", (ratio.width, ratio.height), style.border_rgb)
    for box in solved.gutters:
        # Pasting a colour with a 4-tuple box clips silently at the canvas
        # edge, which matters because an inflated gutter can overhang by a
        # pixel at the outer edge of the block.
        canvas.paste(style.gutter_rgb, (box.x, box.y, box.x + box.width, box.y + box.height))

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
