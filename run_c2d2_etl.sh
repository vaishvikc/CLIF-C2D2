#!/usr/bin/env bash

# setup_and_run.sh — Combined setup and notebook execution script for CLIF project (Mac/Linux)

set -e
set -o pipefail

# ── ANSI colours for pretty output ─────────────────────────────────────────────
YELLOW="\033[33m"
CYAN="\033[36m"
GREEN="\033[32m"
RESET="\033[0m"

separator() {
  echo -e "${YELLOW}==================================================${RESET}"
}

# ── 1. Create virtual environment ──────────────────────────────────────────────
separator
if [ ! -d ".clif_c2d2" ]; then
  echo -e "${CYAN}Creating virtual environment (.clif_c2d2)...${RESET}"
  python3 -m venv .clif_c2d2
else
  echo -e "${CYAN}Virtual environment already exists.${RESET}"
fi

# ── 2. Activate virtual environment ────────────────────────────────────────────
separator
echo -e "${CYAN}Activating virtual environment...${RESET}"
# shellcheck source=/dev/null
source .clif_c2d2/bin/activate

# ── 3. Upgrade pip ─────────────────────────────────────────────────────────────
separator
echo -e "${CYAN}Upgrading pip...${RESET}"
python -m pip install --upgrade pip

# ── 4. Install required packages ───────────────────────────────────────────────
separator
echo -e "${CYAN}Installing dependencies...${RESET}"
pip install --quiet -r requirements.txt
pip install --quiet jupyter ipykernel

# ── 5. Register Jupyter kernel ─────────────────────────────────────────────────
separator
echo -e "${CYAN}Registering Jupyter kernel...${RESET}"
python -m ipykernel install --user --name=.clif_c2d2 --display-name="Python (mobilization)"

# ── 6. Change to code directory ────────────────────────────────────────────────
separator
echo -e "${CYAN}Changing to code directory...${RESET}"
cd etl || { echo "❌  'etl' directory not found."; exit 1; }

# ── 7. Convert and execute notebooks, streaming + logging ──────────────────────
mkdir -p logs

NOTEBOOKS=(
  "01_c2d2_cohort_built.ipynb"
  "06_diagnostic_tests.ipynb"
  "07_interventions.ipynb"
  "08_medications.ipynb"
  "09_objective_assessments.ipynb"
  "10_c2d2_generator.ipynb"
)

for nb in "${NOTEBOOKS[@]}"; do
  base_name="${nb%.ipynb}"
  log_file="logs/${base_name}.log"
  separator
  echo -e "${CYAN}Executing ${nb} and logging output to ${log_file}...${RESET}"
  export MPLBACKEND=Agg
  jupyter nbconvert --to script --stdout "$nb" | python 2>&1 | tee "$log_file"
done

# ── 8. Done ────────────────────────────────────────────────────────────────────
separator
echo -e "${GREEN}✅ All setup and c2d2 genetation completed successfully!${RESET}"

read -rp "Press [Enter] to exit..."