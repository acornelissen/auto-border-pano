# Auto Border Pano

A Python tool for automatically processing panoramic images into social media-ready formats. This tool takes panoramic JPG images and creates four outputs:

1. **Padded Square**: The full panorama in a square frame with 100px side padding and 10px top/bottom padding
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

- Python 3
- Pillow (PIL)

## Installation

1. Clone or download this repository
2. Install the required dependency:

```bash
pip install Pillow
```

## Usage

### Single File Processing

Process a single panoramic image:

```bash
python panorama_splitter.py input_panorama.jpg
```

Process with custom output prefix:

```bash
python panorama_splitter.py input_panorama.jpg my_custom_prefix
```

### Folder Processing

Process all JPG files in a folder:

```bash
python panorama_splitter.py ./input_folder ./output_folder
```

### Examples

1. **Basic single file:**
   ```bash
   python panorama_splitter.py vacation_pano.jpg
   ```
   Creates: `output_1_padded_square.jpg`, `output_2_section1.jpg`, `output_3_section2.jpg`, `output_4_section3.jpg`

2. **Single file with custom prefix:**
   ```bash
   python panorama_splitter.py sunset.jpg hawaii_sunset
   ```
   Creates: `hawaii_sunset_1_padded_square.jpg`, `hawaii_sunset_2_section1.jpg`, etc.

3. **Process entire photo folder:**
   ```bash
   python panorama_splitter.py ~/Pictures/Panoramas ~/Pictures/Panoramas_Processed
   ```
   Processes all JPG files and organizes outputs in the specified folder

## Output Details

### Output 1: Padded Square
- Contains the entire panorama
- Square format with white padding
- 100px padding on left and right sides
- 10px padding on top and bottom
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