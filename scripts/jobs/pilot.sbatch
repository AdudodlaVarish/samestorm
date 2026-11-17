#!/bin/bash
#SBATCH --job-name=samestorm-pilot
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --partition=gpu-a100,gpu-a100-dev
#SBATCH --time=02:00:00
#SBATCH --output=results/raw/slurm-pilot-%j.out
set -euo pipefail

cd "${SAMESTORM_REPO:-$SLURM_SUBMIT_DIR}"
: "${SAMESTORM_PYTHON:?Set to the existing pinned LS6 Python environment}"
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=4
export MKL_NUM_THREADS=4
export OPENBLAS_NUM_THREADS=4
exec "$SAMESTORM_PYTHON" scripts/prepare_pilot_model.py \
    --generate-english-pilot --run-id "pilot-${SLURM_JOB_ID}"
