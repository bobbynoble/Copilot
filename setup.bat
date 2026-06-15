@echo off
echo ============================================
echo  NHS Translation Bot - First-time setup
echo ============================================
echo.
echo Creating virtual environment...
python -m venv venv
echo.
echo Activating virtual environment and installing packages...
call venv\Scripts\activate.bat
pip install -r requirements.txt
echo.
echo ============================================
echo  Setup complete!
echo  Next: edit the .env file with your API keys,
echo  then double-click run_elevenlabs.bat or run_camb.bat
echo ============================================
pause
