@echo off
cd /d "f:\Projects\AI Career Enhancer\AI Career Optimizer"

echo Starting AI Career Optimizer - Complete Pipeline...
echo ===================================================

:: Activate the virtual environment
call venv\Scripts\activate.bat

:: Run the full pipeline (AI cycle + Naukri push)
python main.py --full

echo.
echo Complete Update Pipeline Finished.
pause
