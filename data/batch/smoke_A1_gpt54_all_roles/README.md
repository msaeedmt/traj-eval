# smoke_A1_gpt54_all_roles

This folder is one complete Lean Anchor experiment configuration. Trace files
are intentionally flat and use the same zero-based naming style as
`version_1_trial_traces`.

## Configuration

- Experiment: `lean-anchor-engineer-model-matrix-v1`
- Phase: `smoke`
- Arm: `A1`
- Setup: `recovery_triangle_v1`
- Tasks: 2
- Trials per task: 1
- Expected traces: 2

| Role | Model |
|---|---|
| Reasoner | `openai/gpt-5.4-2026-03-05` |
| Engineer | `openai/gpt-5.4-2026-03-05` |
| Critic | `openai/gpt-5.4-2026-03-05` |

## Evidence status

- Status: **pending**
- Canonical traces present: **0/2**
- Missing traces: **2**
- Recorded error outcomes retained: **0**

Missing filenames are left absent. Future continuation runs may add only those
absent files; existing JSONL files must never be overwritten.

## File contract

- Pattern: `<task_id>_t<zero_based_trial_index>.jsonl`
- Example: `easy_fatem_011_t0.jsonl`
- JSONL contents, internal `trial_id`, and internal `run_id` remain
  byte-identical to the source evidence.

## Source runs

- None yet; this configuration is pending.

The complete original Run/Restart layout, including duplicates, partial traces,
and quota failures, is preserved in Git commit `1dd06c485df34a10db990f051972d7b190e7946e`. The per-file
source paths and SHA-256 values are recorded in
`data/analysis/lean_anchor_engineer_model_matrix_v1/canonicalization_report.v001.json`.

## Correctness and limitations

The primary success condition remains independent Lean kernel verification with
the original statement preserved, no prohibited placeholders, and no additional
axioms. A trace file records an experimental outcome; its presence alone is not
a correctness claim. No new Qwen call is part of this configuration.
