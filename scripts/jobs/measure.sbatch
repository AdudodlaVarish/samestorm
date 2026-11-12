#!/bin/bash
#SBATCH --job-name=samestorm-measure
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --partition=gpu-a100
#SBATCH --time=00:30:00
#SBATCH --output=results/raw/slurm-measure-%j_%a.out
set -euo pipefail
cd "${SAMESTORM_REPO:-$SLURM_SUBMIT_DIR}"
: "${SAMESTORM_PYTHON:?Set to the prepared scale environment}"
: "${SAMESTORM_MODEL_MANIFEST:?Set to the matching successful model-preparation manifest}"
export PYTHONDONTWRITEBYTECODE=1
exec "$SAMESTORM_PYTHON" scripts/throughput.py measure \
    --run-id "measure-${SLURM_JOB_ID}-${SLURM_ARRAY_TASK_ID:-0}" \
    --job-index "${SLURM_ARRAY_TASK_ID:-0}" --model-manifest "$SAMESTORM_MODEL_MANIFEST"
