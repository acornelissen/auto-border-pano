# Masking Frame

![Masking Frame](gui.png)

A masking frame is the darkroom device that holds printing paper under an
enlarger: adjustable blades mask the paper's edges, setting the format and
leaving a white border. This is that, for panoramas bound for Instagram.

It takes a panoramic JPG and creates:

1. **Bordered frame**: The full panorama, fitted inside the target output frame with a border on all sides and centered on the border colour. The border is a percent of the frame's short side — 9% by default, so it reads the same at every ratio — and whichever axis binds gets exactly that, with the other axis getting whatever's left over
2. **Detail frames**: A zoomed, cropped-and-resized view of a horizontal slice of the panorama, at the target aspect ratio. How many of these there are depends on the ratio and the panorama's shape — see [Aspect ratio](#aspect-ratio) below

## Features

- Process single panoramic images or entire folders
- Set the border width and colour, and the gap between composite panels
- Automatic resizing to maximize content at the chosen aspect ratio
- High-quality LANCZOS resampling for crisp output
- Maintains aspect ratio while maximizing visible content
- Batch processing with progress tracking
- Error handling for individual files in batch mode

## Requirements

- [mise](https://mise.jdx.dev) on macOS and Linux, or
  [uv](https://docs.astral.sh/uv/) on Windows

Everything else, including Python itself, is installed for you.

## Installation

**macOS / Linux**

```bash
mise install
mise run setup
```

**Windows**

```batch
install.bat
```

## Usage

**GUI:** `mise run gui` (or `run_gui.bat` on Windows). The window is a
two-tab notebook: **Split** for the single-panorama/batch workflow below,
and **Compose** for composing two or three photos into one frame
(see [Diptychs and triptychs](#diptychs-and-triptychs)).

**CLI:**

```bash
mise run split -- input.jpg my_prefix      # single image
mise run split -- ./panoramas ./output     # whole folder
```

Run `uv run maskingframe --help` for all options. Folder mode writes to
`./output` if you omit the output argument.

### Examples

1. **GUI mode:**
   ```bash
   mise run gui
   ```
   On the **Split** tab:
   - Click "Choose file" to select a single panorama
   - Click "Choose folder" to process multiple images
   - Pick a target ratio
   - Click "Cut frames" to start
   - View previews of the generated images

   Switch to the **Compose** tab to compose two or three photos
   into one frame instead — see
   [Diptychs and triptychs](#diptychs-and-triptychs).

2. **CLI - single file:**
   ```bash
   mise run split -- vacation_pano.jpg --ratio 4:5
   ```
   Creates `output_1_padded.jpg` plus a variable number of
   `output_2_section1.jpg`, `output_3_section2.jpg`, ... — see
   [Aspect ratio](#aspect-ratio) for how many.

3. **CLI - custom prefix:**
   ```bash
   mise run split -- sunset.jpg hawaii_sunset --ratio 1:1
   ```
   Creates: `hawaii_sunset_1_padded.jpg`, `hawaii_sunset_2_section1.jpg`, etc.

4. **CLI - batch processing:**
   ```bash
   mise run split -- ~/Pictures/Panoramas ~/Pictures/Panoramas_Processed --ratio 1.91:1
   ```
   Processes every JPG in the folder once each and organizes outputs in the
   specified folder. If any file fails, the CLI exits non-zero and lists the
   failures on stderr; everything else in the batch still gets processed.

## Aspect ratio

Instagram supports three feed shapes, and every image in a carousel must
share one. Pick the target with `--ratio`, using either the bare ratio or
its name (case-insensitive) — `--ratio 4:5` and `--ratio portrait` are
equivalent:

| Name | Ratio | Output size | Use |
| ---- | ----- | ----------- | --- |
| `portrait` | `4:5` | 1080x1350 | Default. Largest feed footprint. |
| `square` | `1:1` | 1080x1080 | Classic square. |
| `landscape` | `1.91:1` | 1080x566 | Landscape — Instagram's widest feed shape. |

The GUI combobox lists these as "Portrait (4:5)", "Square (1:1)", and
"Landscape (1.91:1)", in that order.

The first frame is the whole panorama on a white canvas. The frames after it
are a zoom, so viewers can see detail that is illegible in the first — and
how many there are is derived from the ratio and the panorama's shape, never
fewer than two.

Measured against 16 of the author's own scans: panoramas around 2.2-2.5:1
give 3 detail frames at 4:5, 2 at 1:1, and 2 at 1.91:1. Panoramas around
2.8-3.0:1 give 4, 3 and 2.

```bash
mise run split -- panorama.jpg my_prefix --ratio 4:5
mise run split -- ./panoramas ./output --ratio 1.91:1
```

Portrait images are rejected — this tool expects landscape panoramas. In a
batch the rejected file is reported and the rest continue.

## Border and gaps

The border is a percent of the frame's short side rather than a fixed pixel
count, so one setting reads the same at every ratio. The default is 9%: 97px
at `4:5` and `1:1`, 51px at `1.91:1`.

| Flag | Default | What it does |
| ---- | ------- | ------------ |
| `--border PERCENT` | `9` | Border width, as a percent of the frame's short side |
| `--border-colour HEX` | `#ffffff` | Border colour, e.g. `#c9302a` or `c9302a` |
| `--gutter PERCENT` | `4` | Composites only: the gap between panels |
| `--gutter-colour HEX` | `#ffffff` | Composites only: the colour of that gap |
| `--border-detail-frames` | off | Border the zoomed detail frames too, not just the first frame |

`--border-color` and `--gutter-color` work as well, if you prefer them. The
CLI splits panoramas only, so the two gutter flags are there for parity with
the GUI's Compose tab, which is where composites are made.

On a composite the two colours cover different things: the gutter colour
fills only the strips between panels, and everything else — the outer margin
and the space left over from centring — takes the border colour.

Both tabs of the GUI have the same Border section, and each remembers what
you last set it to.

```bash
mise run split -- panorama.jpg my_prefix --border 12 --border-colour '#000000'
```

## Diptychs and triptychs

The second tab composes two or three photographs into a single frame at any
of the three ratios.

The layout is chosen for you. The tool tries each sensible arrangement — a
row, a column, and for three images the variants with one large panel beside
two stacked ones — and keeps whichever fills the frame best. Panels are never
cropped: each keeps its own aspect ratio, and whatever space is left over
becomes border. That is what lets a 6x17 panorama, a square 6x6 and a
35mm frame sit in one composite without any of them losing content.

Images stay in the order you arrange them. Use Up and Down to change it.

Unlike the splitter, portrait images are fine here — mixing orientations is
much of the point.

## Output Details

### Output 1: Bordered frame

- Contains the entire panorama, fitted (never cropped) inside the target
  output frame with a border on all sides and centered on a canvas already
  sized to the target output size (same pixel dimensions as the detail
  frames) — a large-format scan doesn't produce a multi-megabyte first frame
  beside sub-megabyte detail frames
- At the default `4:5` ratio, most of the canvas is border by design —
  that's the intended aesthetic, not a bug
- Whichever axis binds gets exactly the border — normally the width, but a
  panorama flatter than the inset box binds on height instead — and the
  other axis gets whatever's left over, usually much more (this is
  deliberate, and locked in place by tests)
- Only square when you ask for `1:1`
- Ideal for Instagram gallery posts

### Outputs 2+: Detail frames

- Each detail frame is exactly the target ratio's output size (e.g.
  1080x1350 at `4:5`)
- The panorama is divided into that many equal horizontal slices; each slice
  is scaled to cover the target size and center-cropped to fit exactly
- Perfect for Instagram carousel posts

## Tips

- Works best with horizontal panoramic images
- Output quality is set to 95% JPEG compression for optimal file size vs quality
- The tool automatically handles various panorama aspect ratios
- For vertical panoramas, consider rotating before processing

## Troubleshooting

- **"No JPG files found"**: Ensure your input folder contains files with .jpg, .JPG, .jpeg, or .JPEG extensions
- **"Error processing image"**: Check that the file is a valid image format and not corrupted
- **Memory issues**: Very large panoramas may require more RAM; consider processing one at a time

## License

This tool is provided as-is for personal and commercial use.