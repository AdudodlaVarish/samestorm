#!/bin/bash
#SBATCH --job-name=samestorm-generate
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --partition=gpu-a100
#SBATCH --time=00:30:00
#SBATCH --output=results/raw/slurm-generate-%j_%a.out
set -euo pipefail

# Prepared only. Submit one selected matrix index after access and execution are authorized.
cd "${SAMESTORM_REPO:-$SLURM_SUBMIT_DIR}"
: "${SAMESTORM_PYTHON:?Set to the scale Python environment}"
: "${SAMESTORM_PACKET:?Set to the prepared generation packet}"
: "${SAMESTORM_REVIEW_MANIFEST:?Set to recorded student review and frozen input hashes}"
: "${SAMESTORM_MODEL_MANIFEST:?Set to the matching model-preparation manifest}"
export PYTHONDONTWRITEBYTECODE=1
exec "$SAMESTORM_PYTHON" scripts/scale_generate.py generate \
    --run-id "generate-${SLURM_JOB_ID}-${SLURM_ARRAY_TASK_ID:-0}" \
    --packet "$SAMESTORM_PACKET" --review-manifest "$SAMESTORM_REVIEW_MANIFEST" \
    --model-manifest "$SAMESTORM_MODEL_MANIFEST" --job-index "${SLURM_ARRAY_TASK_ID:-0}"
