# Diptych and triptych compositor

Date: 2026-07-31
Status: approved, not yet implemented

## Goal

A second GUI tab that composes two or three separate photographs into a
single frame at any of the supported aspect ratios, laying them out
automatically from the images themselves.

## What the user asked for

> It should be clever enough to lay them out automatically depending on the
> images selected and output aspect ratio, and work for all image sizes and
> aspect ratios.

There is therefore no manual layout control. The tool decides.

## Decisions

| Question | Decision |
| -------- | -------- |
| Inputs | Two or three separate photographs |
| Layout | Chosen automatically from the images and the target ratio |
| Cropping | None, ever. Every panel keeps its full composition |
| Leftover space | Becomes white border; the assembled block is centred |
| Image order | Preserved as the user arranged it; never permuted |
| CLI | Not exposed. GUI only |
| Outer margin | `SIDE_PADDING`, 100 output pixels, matching the headline frame |
| Gutter | 40 output pixels |

Cropping nothing is what makes "works for all image sizes and aspect ratios"
achievable: a 6x17 panorama, a square 6x6 and a 35mm frame can share a
composite without any of them losing content.

## The layout solver

A new module, `layout.py`. Pure arithmetic — no PIL, no I/O — so the
interesting logic is fast and trivial to test.

### Representation

A layout is a tree. A node is either a **leaf** (one image, carrying its
aspect ratio) or a **row** or **column** of child nodes. Depth never exceeds
two, since only two and three images are supported.

Candidates for two images:

- `row(A, B)`
- `column(A, B)`

Candidates for three:

- `row(A, B, C)`
- `column(A, B, C)`
- `row(A, column(B, C))`
- `row(column(A, B), C)`
- `column(A, row(B, C))`
- `column(row(A, B), C)`

Image order is fixed, so these six are the complete set. No permutations.

### Solving

Every node can state its width as an affine function of its height:

```text
width = A * height + B
```

- **Leaf** with aspect `a`: `width = a * height`, so `A = a`, `B = 0`.
- **Row** of children with gutter `g`: children share a height, so
  `width = (Σ Aᵢ) * height + (Σ Bᵢ) + (n - 1) * g`.
- **Column** of children with gutter `g`: children share a width `w`, and
  their heights sum to `height - (n - 1) * g`. Inverting each child's
  relation gives `heightᵢ = (w - Bᵢ) / Aᵢ`, so
  `w = (height - (n - 1) * g + Σ (Bᵢ / Aᵢ)) / Σ (1 / Aᵢ)`, which is affine
  in `height`.

The relation stays affine at every level, so a single bottom-up pass gives
the root its `(A, B)`.

To fit the root into an available box `W x H`, take
`height = min(H, (W - B) / A)` and `width = A * height + B`. That fills the
binding axis exactly and leaves slack on the other. A second, top-down pass
assigns each node a concrete rectangle.

### Scoring

Each candidate is scored on how much of the available box its panels cover:

```text
score = Σ (leaf width * leaf height) / (W * H)
```

Highest score wins. Ties break toward the earlier candidate in the list
above, which keeps the result deterministic. Because nothing is cropped,
this is purely a question of which arrangement wastes least white space.

### Interface

```python
solve(aspects: list[float], ratio: AspectRatio, padding: int, gutter: int) -> Layout
```

`Layout` carries the winning candidate's name (for tests and for the GUI to
report) and a `boxes: list[Box]` in input order, each `Box` an integer
`(x, y, width, height)` in output-frame coordinates.

## Rendering

A new module, `compose.py`. Like `geometry.py`, it works in PIL images and
never touches the filesystem: it takes the images plus a solved `Layout` and
returns one PIL image.

Each panel is scaled to its box with `Image.Resampling.LANCZOS` and pasted
onto a white canvas of exactly `(ratio.width, ratio.height)`. The block is
centred, so the slack on the non-binding axis is split evenly.

Panels are scaled to exactly their box dimensions. Because the box aspect
was derived from the image's own aspect, this is a proportional resize, not
a distortion — but the rendering step asserts the two agree within a pixel
of rounding, so a solver bug surfaces as a loud failure rather than a subtly
stretched photograph.

## File I/O

`pipeline.py` gains one function:

```python
compose_images(
    input_paths: list[Path | str],
    output_path: Path | str,
    ratio: AspectRatio = DEFAULT_RATIO,
) -> Path
```

It opens each image, converts to RGB, solves, renders, and saves at
`JPEG_QUALITY`. Two or three paths are accepted; any other count raises
`ValueError`. Unreadable input raises, and the GUI reports it.

Output naming is `{prefix}_diptych.jpg` or `{prefix}_triptych.jpg`.

Unlike the splitter, portrait input is fine here — a composite has no notion
of a panorama, and mixing orientations is exactly what this feature is for.

## GUI restructure

`gui.py` is 289 lines. A second tab would push one file past 500, so it
becomes a package:

```text
src/auto_border_pano/gui/
  __init__.py      re-exports run() and PanoramaSplitterGUI for cli.gui_main
  app.py           the ttk.Notebook shell, owns the root window
  split_tab.py     today's splitter UI, moved essentially unchanged
  compose_tab.py   the new tab
  preview.py       the preview pane grid, shared by both tabs
```

`preview.py` is a genuine extraction, not a speculative one: both tabs need
a row of thumbnail panes that rebuilds as the count changes, which is
already the trickiest widget code in the project.

`cli.gui_main` imports `run` from `auto_border_pano.gui`, so the package's
`__init__` must keep that name working. The tkinter availability guard stays
in `cli.py`; no module in the package may exit the process on import.

The threading discipline is unchanged and non-negotiable: no worker thread
reads or writes any tkinter object, values are read on the main thread and
passed as plain data, and `root.after` is the only crossing back.

## The compose tab

- Add up to three images via a file picker; a list shows them in order.
- Move up / move down / remove, since order is preserved and matters.
- The same labelled ratio selector the splitter uses — Portrait (4:5),
  Square (1:1), Landscape (1.91:1), in that order.
- A preview of the composed result, refreshed when the images, their order,
  or the ratio change.
- The chosen arrangement is named in the status line, so the automatic
  decision is visible rather than mysterious.
- A Save button writing the output beside a chosen prefix.
- Process is disabled unless exactly two or three images are present.

## Testing

The solver carries the weight, because it is pure:

- Two and three equal-aspect images at each ratio produce the arrangement
  that a hand calculation predicts.
- Three 2.33:1 panoramas at 4:5 choose the column, and the resulting panel
  boxes have an aspect within a pixel of 2.33 — proving nothing is cropped.
- A deliberately mixed set — a 3:1 panorama, a 1:1 square and a 0.67:1
  portrait — produces boxes whose aspects each match their source, at every
  ratio. This is the "works for all image sizes and aspect ratios" claim,
  tested directly.
- Boxes never overlap and never escape the frame, checked for every
  candidate at every ratio.
- Scoring picks the higher-filling candidate where the two differ
  measurably, and ties break deterministically.
- Extreme inputs — a 20:1 sliver, a 1:20 tower — still produce valid,
  non-overlapping boxes rather than zero or negative dimensions.

Rendering and I/O:

- The composite is exactly `(ratio.width, ratio.height)`.
- Panel aspect ratios in the output match their sources, measured from the
  rendered image, not from the solver's own numbers.
- Two and three images both work; one or four raise `ValueError`.
- A golden byte-identity test per ratio, matching the existing convention.

GUI:

- Reordering changes the solved layout.
- The tab refuses to process with fewer than two or more than three images.
- The ratio selection reaches the worker as a plain string, on the main
  thread.
- The existing splitter tests keep passing after the move into the package,
  unchanged apart from import paths.

## Out of scope

- Four or more panels
- Manual layout override, or nudging a chosen layout
- Per-panel cropping, zoom or pan
- Captions, borders around individual panels, or drop shadows
- A CLI entry point
- Reordering by drag and drop; buttons are enough

## Success criteria

- `mise run check` green, with the existing suite unaffected by the GUI
  package move.
- Any mix of two or three images, at any aspect ratios, composes without
  cropping and without overlapping.
- The composite is exactly the target ratio, with the block centred and a
  100px outer margin.
- The chosen arrangement is visible in the UI.
- Switching ratio re-solves and re-previews.
- README and CLAUDE.md document the tab, the solver's rule, and the new
  module boundaries.
