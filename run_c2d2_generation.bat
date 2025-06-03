@echo off
SETLOCAL ENABLEDELAYEDEXPANSION

REM ── Step 0: Go to script directory ──
cd /d %~dp0

REM ── Step 1: Create virtual environment if missing ──
if not exist ".clif_c2d2\" (
    echo Creating virtual environment...
    python -m venv .clif_c2d2
) else (
    echo Virtual environment already exists.
)

REM ── Step 2: Activate virtual environment ──
call .clif_c2d2\Scripts\activate.bat

REM ── Step 3: Install required packages ──
echo Installing dependencies...
pip install --quiet -r requirements.txt
pip install --quiet jupyter ipykernel papermill

REM ── Step 4: Register kernel ──
python -m ipykernel install --user --name=.clif_c2d2 --display-name="Python (clif_c2d2)"

REM ── Step 5: Set environment variables ──
set PYTHONWARNINGS=ignore
set PYTHONPATH=%cd%\code;%PYTHONPATH%

REM ── Step 6: Change to code directory ──
cd etl

REM ── Step 7: Create logs folder ──
if not exist logs (
    mkdir logs
)

echo.
echo ✅ All steps completed successfully!
pause
exit /b
