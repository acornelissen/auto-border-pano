# Auto Border Pano

![auto-border-pano GUI](gui.png)

A Python tool for automatically processing panoramic images into social media-ready formats. This tool takes a panoramic JPG image and creates:

1. **Padded frame**: The full panorama, fitted inside the target output frame with a 100px inset on all sides and centered on a white canvas. Whichever axis binds gets exactly 100px of padding — usually the width for a wide panorama, but at `1.91:1` a panorama flatter than the frame's own ratio binds on height instead — and the other axis gets whatever's left over
2. **Detail frames**: A zoomed, cropped-and-resized view of a horizontal slice of the panorama, at the target aspect ratio. How many of these there are depends on the ratio and the panorama's shape — see [Aspect ratio](#aspect-ratio) below

## Features

- Process single panoramic images or entire folders
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

**GUI:** `mise run gui` (or `run_gui.bat` on Windows)

**CLI:**

```bash
mise run split -- input.jpg my_prefix      # single image
mise run split -- ./panoramas ./output     # whole folder
```

Run `uv run pano-split --help` for all options. Folder mode writes to
`./output` if you omit the output argument.

### Examples

1. **GUI mode:**
   ```bash
   mise run gui
   ```
   - Click "Browse File" to select a single panorama
   - Click "Browse Folder" to process multiple images
   - Pick a target ratio
   - Click "Process Images" to start
   - View previews of the generated images

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

## Output Details

### Output 1: Padded frame

- Contains the entire panorama, fitted (never cropped) inside the target
  output frame with a 100px inset on all sides and centered on a white
  canvas already sized to the target output size (same pixel dimensions as
  the detail frames) — a large-format scan doesn't produce a multi-megabyte
  first frame beside sub-megabyte detail frames
- At the default `4:5` ratio, most of the canvas is white border by design —
  that's the intended aesthetic, not a bug
- Whichever axis binds gets exactly 100px of padding — normally the width,
  but at `1.91:1` a panorama flatter than 2.4:1 (this project's own scans
  included) binds on height instead — and the other axis gets whatever's
  left over, usually much more than 100px (this is deliberate, and locked
  in place by tests)
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