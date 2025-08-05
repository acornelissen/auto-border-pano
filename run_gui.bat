@echo off

REM Check if virtual environment exists
if not exist "venv" (
    echo Virtual environment not found. Running installation...
    call install.bat
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Run the GUI
python panorama_splitter_gui.py

REM Keep window open
pause