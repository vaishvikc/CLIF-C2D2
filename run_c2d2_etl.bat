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

REM ── Step 8: Run analysis notebooks using papermill ──
echo.
echo Running 01_c2d2_cohort_built.ipynb ...
papermill 01_c2d2_cohort_built.ipynb 01_c2d2_cohort_built.ipynb > logs\01_c2d2_cohort_built.log
echo Finished 01_c2d2_cohort_built.ipynb

echo.
echo Running 06_diagnostic_tests.ipynb ...
papermill 06_diagnostic_tests.ipynb 06_diagnostic_tests.ipynb > logs\06_diagnostic_tests.log
echo Finished 06_diagnostic_tests.ipynb

echo.
echo Running 07_interventions.ipynb ...
papermill 07_interventions.ipynb 07_interventions.ipynb > logs\07_interventions.log
echo Finished 07_interventions.ipynb

echo.
echo Running 08_medications.ipynb ...
papermill 08_medications.ipynb 08_medications.ipynb > logs\08_medications.log
echo Finished 08_medications.ipynb

echo.
echo Running 09_objective_assessments.ipynb ...
papermill 09_objective_assessments.ipynb 09_objective_assessments.ipynb > logs\09_objective_assessments.log
echo Finished 09_objective_assessments.ipynb

echo.
echo Running 10_c2d2_generator.ipynb ...
papermill 10_c2d2_generator.ipynb 10_c2d2_generator.ipynb > logs\10_c2d2_generator.log
echo Finished 10_c2d2_generator.ipynb

echo.
echo ✅ All steps completed successfully!
pause
exit /b
