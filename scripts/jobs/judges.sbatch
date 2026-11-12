#!/bin/bash
#SBATCH --job-name=samestorm-judge
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --partition=gpu-a100
#SBATCH --time=00:30:00
#SBATCH --output=results/raw/slurm-judge-%j.out
set -euo pipefail

# Prepared only. Supply the real allocation with sbatch -A; this script never submits itself.
cd "${SAMESTORM_REPO:-$SLURM_SUBMIT_DIR}"
: "${SAMESTORM_PYTHON:?Set to the separate pinned LS6 judge environment}"
mode="${1:?Choose probe or judge}"
role="${2:-primary}"
run_id="judge-${SLURM_JOB_ID}-${mode}-${role}"
export PYTHONDONTWRITEBYTECODE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

case "$mode" in
    probe)
        exec "$SAMESTORM_PYTHON" scripts/scale_judge.py probe --run-id "$run_id"
        ;;
    judge)
        : "${SAMESTORM_JUDGE_DIR:?Set to the exact pinned local judge checkpoint}"
        : "${SAMESTORM_TASKS:?Set to the prepared synthetic judge tasks}"
        exec "$SAMESTORM_PYTHON" scripts/scale_judge.py judge --run-id "$run_id" \
            --judge-role "$role" --model-dir "$SAMESTORM_JUDGE_DIR" --input "$SAMESTORM_TASKS" \
            --offset "${SAMESTORM_OFFSET:-0}" --limit "${SAMESTORM_LIMIT:-0}"
        ;;
    *)
        echo "Unknown mode: $mode" >&2
        exit 2
        ;;
esac
