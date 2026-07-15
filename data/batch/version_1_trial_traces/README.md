# Version 1 Lean trial traces

This folder preserves the original 100 Lean trial traces before integrating
the teammate's goal-directed tools. It contains 10 easy tasks with 10 trials
per task (`t0` through `t9`).

## Agent and model

- Architecture: `four_role_multi`
- Backbone: `openai/Qwen3.5-27B-Q5_K_M.gguf`
- Roles: reasoner, engineer, Lean validator, and critic
- Testbed: Lean
- Schema: trajectory schema `0.2.0`

## Tools used in Version 1

- `search_lemmas`: retrieval of relevant Mathlib lemmas
- `check_lean`: Lean compilation and proof checking

The Version 1 traces do not include `try_tactic` or `show_goals`.

## Run configuration

- Trials: 100 total (10 tasks × 10 trials)
- Stress level: 0
- Grounding flag: `false`
- Results: JSONL event traces, one file per task/trial
- Recorded run dates: 2026-07-08

This is the baseline for comparison with the later tool-enabled run. The
runner source and its save-path behavior are unchanged by this archive move.
