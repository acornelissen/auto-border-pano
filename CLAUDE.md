# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python image processing tool that splits panoramic images into social media-ready formats:
1. A square-padded version of the full panorama with 100px side padding and 10px top/bottom padding
2. Three 1080x1080 square sections from the panorama (left, middle, right) that maximize content visibility

## Development Commands

### Running the Script

**Single file processing:**
```bash
# Basic usage
python panorama_splitter.py <input_image.jpg> [output_prefix]

# Example
python panorama_splitter.py horizons3pro-hp5-3.jpg my_output
```

**Folder processing:**
```bash
# Process all JPGs in a folder
python panorama_splitter.py <input_folder> <output_folder>

# Example
python panorama_splitter.py ./input_photos ./output_photos
```

### Dependencies
The project requires Python 3 and the Pillow library:
```bash
pip install Pillow
```

Note: There is no requirements.txt file in the project currently.

## Architecture

This is a single-file Python script (`panorama_splitter.py`) with straightforward architecture:

- **Main entry point**: `main()` function handles CLI arguments and routes to single file or folder processing
- **Core functions**:
  - `process_panoramic_image()`: Processes a single panoramic image into 4 outputs
  - `process_folder()`: Handles batch processing of JPG files in a directory
- **Image processing approach**:
  - Creates a white square canvas with asymmetric padding (100px sides, 10px top/bottom)
  - Splits panorama into thirds and resizes each to fill 1080x1080 squares
  - Uses LANCZOS resampling for high-quality output
  - Maintains aspect ratio while maximizing visible content

Key features:
- Supports batch processing with progress tracking
- Handles various JPG extensions (jpg, JPG, jpeg, JPEG)
- Creates output directories automatically
- Continues processing on individual file errors