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

- Python 3.7 or higher
- Pillow (PIL) for image processing
- tkinter (GUI support) - included with Python on Windows/macOS, requires separate installation on Linux
- macOS: Homebrew package manager (recommended)

## Quick Installation

### Option 1: Automated Installation (Recommended)

**macOS:**
```bash
chmod +x install.sh
./install.sh
```
This will:
- Install Python 3 via Homebrew (if needed)
- Install image processing libraries via Homebrew
- Create a virtual environment
- Install Pillow with proper Homebrew linking
- tkinter is included with Homebrew Python

**Linux:**
```bash
chmod +x install.sh
./install.sh
```
This will:
- Check and install tkinter if needed (python3-tk package)
- Auto-detect your package manager (apt, dnf, yum, zypper, pacman)
- Create a virtual environment
- Install all dependencies

**Windows:**
```batch
install.bat
```

The installer will:
- Set up all dependencies
- Create a virtual environment
- Provide instructions for running the app

### Option 2: Manual Installation

**macOS (using Homebrew):**
```bash
# Install dependencies via Homebrew
brew install python@3 libjpeg libtiff little-cms2 openjpeg webp

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install Pillow with Homebrew libraries
export CPPFLAGS="-I$(brew --prefix)/include"
export LDFLAGS="-L$(brew --prefix)/lib"
pip install -r requirements.txt
```

**Linux/Windows:**
```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # Linux
# or
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
```

## Usage

### GUI Mode (Recommended)

**Quick Launch (auto-activates virtual environment):**
- **macOS/Linux:** `./run_gui.sh`
- **Windows:** `run_gui.bat`

**Or manually:**
```bash
# Activate virtual environment first
source venv/bin/activate  # macOS/Linux
# or
venv\Scripts\activate     # Windows

# Then run the GUI
python panorama_splitter_gui.py
```

Features:
- Visual file/folder selection
- Real-time progress tracking
- Preview of processed images
- Automatic output path suggestions

### Command Line Mode

#### Single File Processing

Process a single panoramic image:

```bash
python panorama_splitter.py input_panorama.jpg
```

Process with custom output prefix:

```bash
python panorama_splitter.py input_panorama.jpg my_custom_prefix
```

#### Folder Processing

Process all JPG files in a folder:

```bash
python panorama_splitter.py ./input_folder ./output_folder
```

### Examples

1. **GUI mode:**
   ```bash
   python panorama_splitter_gui.py
   ```
   - Click "Browse File" to select a single panorama
   - Click "Browse Folder" to process multiple images
   - Click "Process Images" to start
   - View previews of the generated images

2. **Command line - single file:**
   ```bash
   python panorama_splitter.py vacation_pano.jpg
   ```
   Creates: `output_1_padded_square.jpg`, `output_2_section1.jpg`, `output_3_section2.jpg`, `output_4_section3.jpg`

3. **Command line - custom prefix:**
   ```bash
   python panorama_splitter.py sunset.jpg hawaii_sunset
   ```
   Creates: `hawaii_sunset_1_padded_square.jpg`, `hawaii_sunset_2_section1.jpg`, etc.

4. **Command line - batch processing:**
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