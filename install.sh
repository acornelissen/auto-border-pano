#!/bin/bash

echo "==================================="
echo "Panorama Splitter Installation"
echo "==================================="

# Detect OS
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    echo "Detected macOS - using Homebrew for installation"
    
    # Check if Homebrew is installed
    if ! command -v brew &> /dev/null; then
        echo "Error: Homebrew is required but not installed."
        echo "Install it from https://brew.sh/"
        exit 1
    fi
    
    # Check if Python 3 is installed via Homebrew
    if ! brew list python@3 &> /dev/null; then
        echo "Installing Python 3 via Homebrew..."
        brew install python@3
    else
        echo "Python 3 already installed via Homebrew"
    fi
    
    # Install Pillow dependencies via Homebrew
    echo "Installing image processing dependencies..."
    brew install libjpeg libtiff little-cms2 openjpeg webp
    
    # Use Homebrew's Python
    PYTHON_CMD="python3"
    
else
    # Linux
    echo "Detected Linux - using system package manager"
    
    # Check if Python 3 is installed
    if ! command -v python3 &> /dev/null; then
        echo "Error: Python 3 is required but not installed."
        echo "Please install Python 3 using your package manager:"
        echo "  Ubuntu/Debian: sudo apt-get install python3 python3-pip python3-venv"
        echo "  Fedora: sudo dnf install python3 python3-pip"
        echo "  Arch: sudo pacman -S python python-pip"
        exit 1
    fi
    
    # Check if tkinter is available
    if ! python3 -c "import tkinter" &> /dev/null; then
        echo "tkinter not found. Installing tkinter..."
        if command -v apt-get &> /dev/null; then
            echo "Using apt-get to install python3-tk..."
            sudo apt-get update && sudo apt-get install -y python3-tk
        elif command -v dnf &> /dev/null; then
            echo "Using dnf to install python3-tkinter..."
            sudo dnf install -y python3-tkinter
        elif command -v yum &> /dev/null; then
            echo "Using yum to install tkinter..."
            sudo yum install -y tkinter
        elif command -v zypper &> /dev/null; then
            echo "Using zypper to install python3-tk..."
            sudo zypper install -y python3-tk
        elif command -v pacman &> /dev/null; then
            echo "Using pacman to install tk..."
            sudo pacman -S tk
        else
            echo "Could not detect package manager. Please install tkinter manually:"
            echo "  Ubuntu/Debian: sudo apt-get install python3-tk"
            echo "  Fedora: sudo dnf install python3-tkinter"
            echo "  Arch: sudo pacman -S tk"
            echo "  SUSE: sudo zypper install python3-tk"
            exit 1
        fi
        
        # Verify tkinter installation
        if ! python3 -c "import tkinter" &> /dev/null; then
            echo "Error: tkinter installation failed. Please install manually."
            exit 1
        else
            echo "tkinter installed successfully!"
        fi
    else
        echo "tkinter already available"
    fi
    
    PYTHON_CMD="python3"
fi

# Create virtual environment
echo "Creating virtual environment..."
$PYTHON_CMD -m venv venv

# Activate virtual environment
echo "Activating virtual environment..."
if [[ "$OSTYPE" == "darwin"* ]] || [[ "$OSTYPE" == "linux-gnu"* ]]; then
    source venv/bin/activate
else
    echo "Unsupported OS type: $OSTYPE"
    exit 1
fi

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install Pillow
echo "Installing Pillow..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    # On macOS, ensure Pillow uses Homebrew's libraries
    export CPPFLAGS="-I$(brew --prefix)/include"
    export LDFLAGS="-L$(brew --prefix)/lib"
fi
pip install -r requirements.txt

echo ""
echo "==================================="
echo "Installation complete!"
echo "==================================="
echo ""
echo "To use the application:"
echo ""
echo "1. Activate the virtual environment:"
if [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
    echo "   venv\\Scripts\\activate"
else
    echo "   source venv/bin/activate"
fi
echo ""
echo "2. Run the GUI version:"
echo "   python panorama_splitter_gui.py"
echo ""
echo "3. Or use the command line version:"
echo "   python panorama_splitter.py <input.jpg> [output_prefix]"
echo ""
echo "4. When done, deactivate the virtual environment:"
echo "   deactivate"
echo ""