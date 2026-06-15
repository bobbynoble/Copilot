@echo off
echo Starting ElevenLabs NHS Translation Bot on http://localhost:8002 ...
call venv\Scripts\activate.bat
python -m uvicorn nhs_elevenlabs.main:app --port 8002 --host 0.0.0.0
pause
