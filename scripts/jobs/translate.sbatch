#!/bin/bash
#SBATCH --job-name=samestorm-translate
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --partition=gpu-a100
#SBATCH --time=00:30:00
#SBATCH --output=results/raw/slurm-translate-%j.out
set -euo pipefail
cd "${SAMESTORM_REPO:-$SLURM_SUBMIT_DIR}"
: "${SAMESTORM_PYTHON:?Set to the pinned scale environment}"
: "${SAMESTORM_TASKS:?Set to the system-specific response translation tasks}"
: "${SAMESTORM_TRANSLATOR_DIR:?Set to the exact pinned official checkpoint}"
system="${1:?Choose nllb13b, madlad3b or vinai_vi2en}"
export PYTHONDONTWRITEBYTECODE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
exec "$SAMESTORM_PYTHON" scripts/scale_translate.py --system "$system" \
    --tasks "$SAMESTORM_TASKS" --model-dir "$SAMESTORM_TRANSLATOR_DIR" \
    --run-id "translate-${SLURM_JOB_ID}-${system}"
