#!/bin/bash

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Running installation..."
    ./install.sh
fi

# Activate virtual environment
source venv/bin/activate

# Run the GUI
python panorama_splitter_gui.py

# Keep terminal open if app crashes
read -p "Press Enter to exit..."