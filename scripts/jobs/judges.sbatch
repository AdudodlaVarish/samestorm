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
mode="${1:?Choose probe, judge, validate or quantity}"
role="${2:-primary}"
cases="${SAMESTORM_CASES:-data/grading/cases.jsonl}"
prompt_version="${SAMESTORM_JUDGE_PROMPT_VERSION:-v1}"
run_id="judge-${SLURM_JOB_ID}-${mode}-${role}"
export PYTHONDONTWRITEBYTECODE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

case "$mode" in
    validate)
        : "${SAMESTORM_PRIMARY_JUDGE_DIR:?Set to the pinned primary judge checkpoint}"
        : "${SAMESTORM_SECONDARY_JUDGE_DIR:?Set to the pinned secondary judge checkpoint}"
        : "${SAMESTORM_TASKS:?Set to the prepared synthetic validation tasks}"
        if [[ "${SAMESTORM_TASK_KIND:-validation}" != validation ]]; then
            echo 'validate requires synthetic validation tasks shared by both judges.' >&2
            exit 2
        fi
        SAMESTORM_JUDGE_DIR="$SAMESTORM_PRIMARY_JUDGE_DIR" bash "$0" judge primary
        SAMESTORM_JUDGE_DIR="$SAMESTORM_SECONDARY_JUDGE_DIR" bash "$0" judge secondary
        exec "$SAMESTORM_PYTHON" scripts/validate_judges.py \
            --run-id "judge-${SLURM_JOB_ID}-comparison" \
            --cases "$cases" \
            --prompt-version "$prompt_version" \
            --primary "results/raw/judge-${SLURM_JOB_ID}-judge-primary/judgments.jsonl" \
            --secondary "results/raw/judge-${SLURM_JOB_ID}-judge-secondary/judgments.jsonl"
        ;;
    quantity)
        : "${SAMESTORM_PRIMARY_JUDGE_DIR:?Set to the pinned primary judge checkpoint}"
        : "${SAMESTORM_SECONDARY_JUDGE_DIR:?Set to the pinned secondary judge checkpoint}"
        export SAMESTORM_TASK_KIND=quantity
        export SAMESTORM_JUDGE_PROMPT_VERSION=v1
        report_answer_args=()
        for source in "${SAMESTORM_REFERENCE_ANSWERS:-}" "${SAMESTORM_QUANTIZED_ANSWERS:-}"; do
            if [[ -n "$source" ]]; then report_answer_args+=(--answers "$source"); fi
        done
        quantity_status=0
        SAMESTORM_JUDGE_DIR="$SAMESTORM_PRIMARY_JUDGE_DIR" bash "$0" judge primary || quantity_status=1
        SAMESTORM_JUDGE_DIR="$SAMESTORM_SECONDARY_JUDGE_DIR" bash "$0" judge secondary || quantity_status=1
        "$SAMESTORM_PYTHON" scripts/validate_quantities.py report \
            --run-id "quantity-${SLURM_JOB_ID}-comparison" --cases "$cases" \
            "${report_answer_args[@]}" \
            --primary "results/raw/judge-${SLURM_JOB_ID}-judge-primary/judgments.jsonl" \
            --secondary "results/raw/judge-${SLURM_JOB_ID}-judge-secondary/judgments.jsonl"
        exit "$quantity_status"
        ;;
    probe)
        exec "$SAMESTORM_PYTHON" scripts/scale_judge.py probe --run-id "$run_id" \
            --prompt-version "$prompt_version"
        ;;
    judge)
        : "${SAMESTORM_JUDGE_DIR:?Set to the exact pinned local judge checkpoint}"
        : "${SAMESTORM_TASKS:?Set to the prepared synthetic judge tasks}"
        answer_args=()
        if [[ "${SAMESTORM_TASK_KIND:-validation}" == quantity ]]; then
            for source in "${SAMESTORM_REFERENCE_ANSWERS:-}" "${SAMESTORM_QUANTIZED_ANSWERS:-}"; do
                if [[ -n "$source" ]]; then answer_args+=(--answer-file "$source"); fi
            done
        fi
        exec "$SAMESTORM_PYTHON" scripts/scale_judge.py judge --run-id "$run_id" \
            "${answer_args[@]}" \
            --judge-role "$role" --model-dir "$SAMESTORM_JUDGE_DIR" --input "$SAMESTORM_TASKS" \
            --cases "$cases" \
            --prompt-version "$prompt_version" \
            --task-kind "${SAMESTORM_TASK_KIND:-validation}" \
            --offset "${SAMESTORM_OFFSET:-0}" --limit "${SAMESTORM_LIMIT:-0}"
        ;;
    *)
        echo "Unknown mode: $mode" >&2
        exit 2
        ;;
esac
