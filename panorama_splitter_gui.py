#!/usr/bin/env python3
"""
Panoramic Image Splitter GUI
A graphical interface for the panorama splitting tool
"""

import sys
import os

# Check if tkinter is available
try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except ImportError:
    print("Error: tkinter is not installed.")
    print("\ntkinter is required for the GUI but is not available.")
    print("Please install it using your system package manager:\n")
    print("Ubuntu/Debian:")
    print("  sudo apt-get install python3-tk")
    print("\nFedora:")
    print("  sudo dnf install python3-tkinter")
    print("\nArch Linux:")
    print("  sudo pacman -S tk")
    print("\nSUSE:")
    print("  sudo zypper install python3-tk")
    print("\nmacOS (Homebrew):")
    print("  brew install python-tk")
    print("\nAlternatively, use the command-line version:")
    print("  python panorama_splitter.py <input.jpg> [output_prefix]")
    sys.exit(1)

import threading
from PIL import Image, ImageTk
from panorama_splitter import process_panoramic_image, process_folder

class PanoramaSplitterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Panorama Splitter")
        self.root.geometry("800x600")
        
        # Variables
        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.is_folder_mode = tk.BooleanVar(value=False)
        self.progress = tk.DoubleVar()
        self.current_file = tk.StringVar(value="Ready")
        
        self.setup_ui()
        
    def setup_ui(self):
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # Input Section
        ttk.Label(main_frame, text="Input:").grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.input_path, width=50).grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(main_frame, text="Browse File", command=self.browse_file).grid(row=0, column=2, padx=5)
        ttk.Button(main_frame, text="Browse Folder", command=self.browse_folder).grid(row=0, column=3, padx=5)
        
        # Output Section
        ttk.Label(main_frame, text="Output:").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.output_path, width=50).grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(main_frame, text="Browse", command=self.browse_output).grid(row=1, column=2, padx=5)
        
        # Mode indicator
        self.mode_label = ttk.Label(main_frame, text="Mode: Single File")
        self.mode_label.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=10)
        
        # Process button
        self.process_btn = ttk.Button(main_frame, text="Process Images", command=self.process_images, style="Accent.TButton")
        self.process_btn.grid(row=3, column=0, columnspan=4, pady=20)
        
        # Progress section
        progress_frame = ttk.LabelFrame(main_frame, text="Progress", padding="10")
        progress_frame.grid(row=4, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=10)
        progress_frame.columnconfigure(0, weight=1)
        
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress, maximum=100)
        self.progress_bar.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=5)
        
        self.status_label = ttk.Label(progress_frame, textvariable=self.current_file)
        self.status_label.grid(row=1, column=0, sticky=tk.W)
        
        # Preview section
        preview_frame = ttk.LabelFrame(main_frame, text="Preview (Last Processed)", padding="10")
        preview_frame.grid(row=5, column=0, columnspan=4, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.columnconfigure(1, weight=1)
        preview_frame.columnconfigure(2, weight=1)
        preview_frame.columnconfigure(3, weight=1)
        preview_frame.rowconfigure(0, weight=1)
        
        # Preview labels
        self.preview_labels = []
        preview_titles = ["Padded Square", "Left Section", "Middle Section", "Right Section"]
        for i in range(4):
            frame = ttk.Frame(preview_frame)
            frame.grid(row=0, column=i, padx=5, pady=5, sticky=(tk.N, tk.S, tk.E, tk.W))
            
            ttk.Label(frame, text=preview_titles[i], font=("Arial", 10, "bold")).pack()
            
            label = ttk.Label(frame, text="No preview", relief="sunken", anchor="center")
            label.pack(expand=True, fill="both")
            self.preview_labels.append(label)
        
        # Configure row weights for preview
        main_frame.rowconfigure(5, weight=1)
        
    def browse_file(self):
        filename = filedialog.askopenfilename(
            title="Select Panorama Image",
            filetypes=[("Image files", "*.jpg *.jpeg *.JPG *.JPEG"), ("All files", "*.*")]
        )
        if filename:
            self.input_path.set(filename)
            self.is_folder_mode.set(False)
            self.mode_label.config(text="Mode: Single File")
            # Auto-set output prefix
            base = os.path.splitext(filename)[0]
            self.output_path.set(base + "_output")
            
    def browse_folder(self):
        folder = filedialog.askdirectory(title="Select Input Folder")
        if folder:
            self.input_path.set(folder)
            self.is_folder_mode.set(True)
            self.mode_label.config(text="Mode: Folder Processing")
            # Auto-set output folder
            parent = os.path.dirname(folder)
            folder_name = os.path.basename(folder)
            self.output_path.set(os.path.join(parent, folder_name + "_output"))
            
    def browse_output(self):
        if self.is_folder_mode.get():
            folder = filedialog.askdirectory(title="Select Output Folder")
            if folder:
                self.output_path.set(folder)
        else:
            # For single file, just let them choose a folder and we'll add the prefix
            folder = filedialog.askdirectory(title="Select Output Folder")
            if folder:
                input_file = self.input_path.get()
                if input_file:
                    base = os.path.splitext(os.path.basename(input_file))[0]
                    self.output_path.set(os.path.join(folder, base))
                    
    def update_preview(self, output_prefix):
        """Update preview images after processing"""
        preview_files = [
            f"{output_prefix}_1_padded_square.jpg",
            f"{output_prefix}_2_section1.jpg",
            f"{output_prefix}_3_section2.jpg",
            f"{output_prefix}_4_section3.jpg"
        ]
        
        for i, (label, filepath) in enumerate(zip(self.preview_labels, preview_files)):
            if os.path.exists(filepath):
                try:
                    # Load and resize image for preview
                    img = Image.open(filepath)
                    # Calculate size to fit in preview
                    max_size = 150
                    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                    
                    # Convert to PhotoImage
                    photo = ImageTk.PhotoImage(img)
                    label.config(image=photo, text="")
                    label.image = photo  # Keep a reference
                except Exception as e:
                    label.config(image="", text=f"Error: {str(e)}")
            else:
                label.config(image="", text="No preview")
                
    def process_single_file(self):
        """Process a single file in a thread"""
        input_file = self.input_path.get()
        output_prefix = self.output_path.get()
        
        if not input_file or not os.path.exists(input_file):
            messagebox.showerror("Error", "Please select a valid input file")
            return
            
        try:
            self.current_file.set(f"Processing: {os.path.basename(input_file)}")
            process_panoramic_image(input_file, output_prefix)
            self.progress.set(100)
            self.current_file.set("Complete!")
            
            # Update preview
            self.root.after(0, self.update_preview, output_prefix)
            
            messagebox.showinfo("Success", "Image processed successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Error processing image: {str(e)}")
        finally:
            self.process_btn.config(state="normal")
            
    def process_folder_batch(self):
        """Process a folder of files in a thread"""
        input_folder = self.input_path.get()
        output_folder = self.output_path.get()
        
        if not input_folder or not os.path.exists(input_folder):
            messagebox.showerror("Error", "Please select a valid input folder")
            return
            
        # Create output folder
        os.makedirs(output_folder, exist_ok=True)
        
        # Find all JPG files
        import glob
        jpg_patterns = ['*.jpg', '*.JPG', '*.jpeg', '*.JPEG']
        jpg_files = []
        for pattern in jpg_patterns:
            jpg_files.extend(glob.glob(os.path.join(input_folder, pattern)))
            
        if not jpg_files:
            messagebox.showwarning("Warning", "No JPG files found in the selected folder")
            self.process_btn.config(state="normal")
            return
            
        total_files = len(jpg_files)
        last_output_prefix = None
        
        try:
            for i, jpg_file in enumerate(jpg_files, 1):
                self.current_file.set(f"Processing {i}/{total_files}: {os.path.basename(jpg_file)}")
                self.progress.set((i-1) / total_files * 100)
                
                base_name = os.path.splitext(os.path.basename(jpg_file))[0]
                output_prefix = os.path.join(output_folder, base_name)
                
                try:
                    process_panoramic_image(jpg_file, output_prefix)
                    last_output_prefix = output_prefix
                except Exception as e:
                    print(f"Error processing {jpg_file}: {e}")
                    
            self.progress.set(100)
            self.current_file.set(f"Complete! Processed {total_files} files")
            
            # Update preview with last processed image
            if last_output_prefix:
                self.root.after(0, self.update_preview, last_output_prefix)
                
            messagebox.showinfo("Success", f"Processed {total_files} images successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Error during batch processing: {str(e)}")
        finally:
            self.process_btn.config(state="normal")
            
    def process_images(self):
        """Main process function that runs in a thread"""
        # Disable button during processing
        self.process_btn.config(state="disabled")
        self.progress.set(0)
        
        # Run processing in a separate thread to keep GUI responsive
        if self.is_folder_mode.get():
            thread = threading.Thread(target=self.process_folder_batch)
        else:
            thread = threading.Thread(target=self.process_single_file)
            
        thread.start()

def main():
    root = tk.Tk()
    app = PanoramaSplitterGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()