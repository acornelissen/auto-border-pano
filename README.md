# Auto Border Pano

![auto-border-pano GUI](gui.png)

A Python tool for automatically processing panoramic images into social media-ready formats. This tool takes panoramic JPG images and creates four outputs:

1. **Padded Square**: The full panorama, centered on a white square canvas that is 200px wider than the image. For a normal wide panorama this gives exactly 100px of padding on the left and right, and a larger leftover gap top and bottom
2. **Left Section**: A 1080x1080 square crop of the left third of the panorama
3. **Middle Section**: A 1080x1080 square crop of the middle third of the panorama
4. **Right Section**: A 1080x1080 square crop of the right third of the panorama

## Features

- Process single panoramic images or entire folders
- Automatic resizing to maximize content in square format
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
   - Click "Process Images" to start
   - View previews of the generated images

2. **CLI - single file:**
   ```bash
   mise run split -- vacation_pano.jpg
   ```
   Creates: `output_1_padded_square.jpg`, `output_2_section1.jpg`, `output_3_section2.jpg`, `output_4_section3.jpg`

3. **CLI - custom prefix:**
   ```bash
   mise run split -- sunset.jpg hawaii_sunset
   ```
   Creates: `hawaii_sunset_1_padded_square.jpg`, `hawaii_sunset_2_section1.jpg`, etc.

4. **CLI - batch processing:**
   ```bash
   mise run split -- ~/Pictures/Panoramas ~/Pictures/Panoramas_Processed
   ```
   Processes every JPG in the folder once each and organizes outputs in the
   specified folder. If any file fails, the CLI exits non-zero and lists the
   failures on stderr; everything else in the batch still gets processed.

## Output Details

### Output 1: Padded Square
- Contains the entire panorama, centered on a white square canvas
- The canvas is `max(width + 200px, height + 20px)` on a side, so for any
  normal wide panorama the width term wins
- That gives exactly 100px of padding on the left and right, and a larger
  leftover gap top and bottom (not 10px — this is deliberate, and locked
  in place by tests)
- Ideal for Instagram gallery posts

### Outputs 2-4: Three Sections
- Each section is 1080x1080 pixels (Instagram optimal)
- Divides panorama into three equal horizontal sections
- Resizes to show maximum content while maintaining aspect ratio
- Centers content when cropping to square
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