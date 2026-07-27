# pilot_A4_devstral_all_roles

This folder is one complete Lean Anchor experiment configuration. Trace files
are intentionally flat and use the same zero-based naming style as
`version_1_trial_traces`.

## Configuration

- Experiment: `lean-anchor-engineer-model-matrix-v1`
- Phase: `all_task_pilot`
- Arm: `A4`
- Setup: `recovery_triangle_v1`
- Tasks: 20
- Trials per task: 3
- Expected traces: 60

| Role | Model |
|---|---|
| Reasoner | `mistral/devstral-2512` |
| Engineer | `mistral/devstral-2512` |
| Critic | `mistral/devstral-2512` |

## Evidence status

- Status: **trace set complete**
- Canonical traces present: **60/60**
- Missing traces: **0**
- Recorded error outcomes retained: **7**

Missing filenames are left absent. Future continuation runs may add only those
absent files; existing JSONL files must never be overwritten.

## File contract

- Pattern: `<task_id>_t<zero_based_trial_index>.jsonl`
- Example: `easy_fatem_011_t0.jsonl`
- JSONL contents, internal `trial_id`, and internal `run_id` remain
  byte-identical to the source evidence.

## Source runs

- `lae-mm-v1_all_task_pilot_A4_20260726T043403Z`

The complete original Run/Restart layout, including duplicates, partial traces,
and quota failures, is preserved in Git commit `1dd06c485df34a10db990f051972d7b190e7946e`. The per-file
source paths and SHA-256 values are recorded in
`data/analysis/lean_anchor_engineer_model_matrix_v1/canonicalization_report.v001.json`.

## Correctness and limitations

The primary success condition remains independent Lean kernel verification with
the original statement preserved, no prohibited placeholders, and no additional
axioms. A trace file records an experimental outcome; its presence alone is not
a correctness claim. No new Qwen call is part of this configuration.
