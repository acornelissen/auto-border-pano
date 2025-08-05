#!/usr/bin/env python3
"""
Panoramic Image Splitter
Takes a panoramic JPG and outputs:
1. Main panoramic image in 1:1 frame with 10px padding
2-4. Three 1:1 sections of the panoramic image
"""

import sys
import os
import glob
from PIL import Image

def process_panoramic_image(input_path, output_prefix="output"):
    """
    Process a panoramic image into 4 separate images.
    
    Args:
        input_path: Path to the input panoramic JPG
        output_prefix: Prefix for output files
    """
    # Load the image
    img = Image.open(input_path)
    width, height = img.size
    
    print(f"Original image size: {width}x{height}")
    
    # Output 1: Main panoramic in 1:1 frame with 100px padding on sides, 10px top/bottom
    # Calculate the size needed for the square frame
    # For width: add 200px (100px on each side)
    # For height: add 20px (10px on top and bottom)
    padded_width = width + 200
    padded_height = height + 20
    max_dim = max(padded_width, padded_height)
    
    # Create a new square image with white background
    square_img = Image.new('RGB', (max_dim, max_dim), 'white')
    
    # Calculate position to center the panoramic image
    x_offset = (max_dim - width) // 2
    y_offset = (max_dim - height) // 2
    
    # Paste the panoramic image onto the square canvas
    square_img.paste(img, (x_offset, y_offset))
    
    # Save the padded square image
    output1_path = f"{output_prefix}_1_padded_square.jpg"
    square_img.save(output1_path, 'JPEG', quality=95)
    print(f"Saved: {output1_path} ({max_dim}x{max_dim})")
    
    # Outputs 2-4: Split panoramic into three 1:1 sections
    # Calculate the width of each section
    section_width = width // 3
    
    # For maximum content, we want the largest square that fits the height
    # This means we'll use the full height and resize if needed
    output_size = 1080  # Standard square size for social media
    
    for i in range(3):
        x_start = i * section_width
        x_end = x_start + section_width
        
        # Crop the section from the original (full height)
        section_crop = img.crop((x_start, 0, x_end, height))
        
        # Calculate the aspect ratio of this section
        crop_width = x_end - x_start
        crop_height = height
        
        # We want to fill a square, so we need to determine how to scale
        # to maximize content while maintaining aspect ratio
        if crop_width > crop_height:
            # Wider than tall - scale based on height to fill square
            scale_factor = output_size / crop_height
            new_width = int(crop_width * scale_factor)
            new_height = output_size
            
            # Resize the section
            resized = section_crop.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Crop to square (center horizontally)
            x_offset = (new_width - output_size) // 2
            final_section = resized.crop((x_offset, 0, x_offset + output_size, output_size))
        else:
            # Taller than wide or square - scale based on width to fill square
            scale_factor = output_size / crop_width
            new_width = output_size
            new_height = int(crop_height * scale_factor)
            
            # Resize the section
            resized = section_crop.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Crop to square (center vertically)
            y_offset = (new_height - output_size) // 2
            final_section = resized.crop((0, y_offset, output_size, y_offset + output_size))
        
        # Save the section
        output_path = f"{output_prefix}_{i+2}_section{i+1}.jpg"
        final_section.save(output_path, 'JPEG', quality=95)
        print(f"Saved: {output_path} ({output_size}x{output_size})")

def process_folder(input_folder, output_folder):
    """
    Process all JPG files in a folder.
    
    Args:
        input_folder: Path to folder containing JPG files
        output_folder: Path to folder where output files will be saved
    """
    # Create output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)
    
    # Find all JPG files in the input folder
    jpg_patterns = ['*.jpg', '*.JPG', '*.jpeg', '*.JPEG']
    jpg_files = []
    for pattern in jpg_patterns:
        jpg_files.extend(glob.glob(os.path.join(input_folder, pattern)))
    
    if not jpg_files:
        print(f"No JPG files found in '{input_folder}'")
        return
    
    print(f"Found {len(jpg_files)} JPG file(s) to process")
    
    # Process each file
    for i, jpg_file in enumerate(jpg_files, 1):
        print(f"\nProcessing file {i}/{len(jpg_files)}: {os.path.basename(jpg_file)}")
        
        # Create output prefix based on input filename
        base_name = os.path.splitext(os.path.basename(jpg_file))[0]
        output_prefix = os.path.join(output_folder, base_name)
        
        try:
            process_panoramic_image(jpg_file, output_prefix)
        except Exception as e:
            print(f"Error processing {jpg_file}: {e}")
            continue

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  Single file:  python panorama_splitter.py <input_image.jpg> [output_prefix]")
        print("  Folder:       python panorama_splitter.py <input_folder> <output_folder>")
        print("\nExamples:")
        print("  python panorama_splitter.py panorama.jpg my_output")
        print("  python panorama_splitter.py ./input_photos ./output_photos")
        sys.exit(1)
    
    input_path = sys.argv[1]
    
    if not os.path.exists(input_path):
        print(f"Error: Path '{input_path}' not found")
        sys.exit(1)
    
    # Check if input is a directory
    if os.path.isdir(input_path):
        if len(sys.argv) < 3:
            print("Error: Output folder must be specified when processing a folder")
            print("Usage: python panorama_splitter.py <input_folder> <output_folder>")
            sys.exit(1)
        
        output_folder = sys.argv[2]
        process_folder(input_path, output_folder)
        print("\nAll files processed!")
    else:
        # Single file processing
        output_prefix = sys.argv[2] if len(sys.argv) > 2 else "output"
        
        try:
            process_panoramic_image(input_path, output_prefix)
            print("\nProcessing complete!")
        except Exception as e:
            print(f"Error processing image: {e}")
            sys.exit(1)

if __name__ == "__main__":
    main()