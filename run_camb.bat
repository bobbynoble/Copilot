@echo off
echo Starting camb.ai NHS Translation Bot on http://localhost:8001 ...
call venv\Scripts\activate.bat
python -m uvicorn nhs_translation.main:app --port 8001 --host 0.0.0.0
pause
