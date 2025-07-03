#!/usr/bin/env bash
#SBATCH --partition=dllabdlc_gpu-rtx2080
#SBATCH --job-name=mensa_download
#SBATCH --time=10:00
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --export=ALL
#SBATCH --output=/work/dlclarge2/matusd-dl_lab_project/LOGS//%x.%N.%A.%a.out
#SBATCH --error=/work/dlclarge2/matusd-dl_lab_project/LOGS//%x.%N.%A.%a.err
#SBATCH --array=0-4

# update working_dir and conda_base, remeber to change the path in output and error slurm commands too!!
WORKING_DIR=/work/dlclarge2/matusd-dl_lab_project
CONDA_BASE=/home/matusd/.conda
ENV_NAME=mensa
PYTHON_BIN="$CONDA_BASE/envs/$ENV_NAME/bin/python"
PYTHON_SCRIPT="$WORKING_DIR/scrape.py"   
OUT_DIR="$WORKING_DIR/images"                  
CSV_PREFIX="meals_raw"                          

set -eu
# ───────── argument check ─────────
if [[ $# -ne 1 ]]; then
  echo "Usage: sbatch $0 TOTAL_DAYS" >&2
  exit 1
fi
TOTAL_DAYS="$1"           # e.g. 100
CHUNKS=5
CHUNK_SIZE=$(( (TOTAL_DAYS + CHUNKS - 1) / CHUNKS ))   # ceil(TOTAL/5)

TASK_ID=${SLURM_ARRAY_TASK_ID}

# ───────── skip idle tasks ─────────
OFFSET_START=$(( TASK_ID * CHUNK_SIZE ))
if (( OFFSET_START >= TOTAL_DAYS )); then
  echo "Task $TASK_ID: nothing to do (window smaller than $((TASK_ID+1))*chunk)"
  exit 0
fi

OFFSET_STOP=$(( OFFSET_START + CHUNK_SIZE - 1 ))
if (( OFFSET_STOP >= TOTAL_DAYS )); then
  OFFSET_STOP=$(( TOTAL_DAYS - 1 ))
fi

# ───────── date range calculation ─────────
TODAY=$(date +%F)
START_DATE=$(date +%F -d "${TODAY} -${OFFSET_START} days")
STOP_DATE=$(date  +%F -d "${TODAY} -${OFFSET_STOP} days")

echo "Task $TASK_ID scraping $STOP_DATE … $START_DATE"

# ───────── run scraper ─────────
source "$CONDA_BASE"/bin/activate "$ENV_NAME"

mkdir -p "$OUT_DIR"

CSV_NAME="${CSV_PREFIX}_task_${TASK_ID}"

cd "$WORKING_DIR"

"$PYTHON_BIN" "$PYTHON_SCRIPT" \
    --start "$START_DATE" \
    --stop  "$STOP_DATE" \
    -o "$OUT_DIR" \
    -c "$CSV_NAME"