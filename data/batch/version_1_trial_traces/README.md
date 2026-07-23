# Version 1 Lean trial traces

This directory preserves the original 100 easy-task Lean traces as a
self-contained raw cohort: 10 tasks with 10 trials per task (`t0` through
`t9`).

## Recorded configuration

- Trace schema: `0.2.0`
- Historical architecture label: `four_role_multi`
- Reasoning roles: Reasoner, Engineer, and Critic
- Tool runtime: recorded as `executor` in the legacy trace schema; it is not a
  reasoning agent
- Backbone: `openai/Qwen3.5-27B-Q5_K_M.gguf`
- Testbed: Lean
- Recorded run date: July 8, 2026

The recorded tools were `search_lemmas` and `check_lean`; these traces predate
the later `try_tactic` and `show_goals` additions.

The directory name records dataset provenance only. It does not make this
cohort a controlled comparison with later runs.
