@echo off
echo ===================================
echo Panorama Splitter Installation
echo ===================================

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python is required but not installed.
    echo Please install Python 3 from https://www.python.org/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

REM Create virtual environment
echo Creating virtual environment...
python -m venv venv

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install requirements
echo Installing dependencies...
pip install -r requirements.txt

echo.
echo ===================================
echo Installation complete!
echo ===================================
echo.
echo To use the application:
echo.
echo 1. Activate the virtual environment:
echo    venv\Scripts\activate.bat
echo.
echo 2. Run the GUI version:
echo    python panorama_splitter_gui.py
echo.
echo 3. Or use the command line version:
echo    python panorama_splitter.py input.jpg [output_prefix]
echo.
echo 4. When done, deactivate the virtual environment:
echo    deactivate
echo.
pause