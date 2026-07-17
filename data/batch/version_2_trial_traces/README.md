# Version 2 goal-tool trial traces

This directory accumulates the Qwen trials run after adding the teammate's
kernel-backed `try_tactic` and `show_goals` tools. The runner still wrote to an
explicit experiment directory; its project default remains `data/batch`.

## Configuration

- Model: `openai/Qwen3.5-27B-Q5_K_M.gguf`
- Team: Reasoner, Engineer, Lean executor, Critic
- Setup: `recovery_triangle_v1`
- Tools: `search_lemmas`, `check_lean`, `try_tactic`, `show_goals`
- Dataset import context: the task's Mathlib imports
- Top-level trials: 30-turn budget
- `200_turns/`: 200-turn diagnostic budget

The ten `easy_fatem_019_t0` through `t9` traces predate the explicit
`worker_enable_thinking` metadata field. The `easy_fatem_020` traces record
thinking as disabled. All files parse under trace schema `0.2.0`, but this
legacy runner did not append an explicit terminal event.

## Inventory and status

- `easy_fatem_019_t0` through `t9`: ten completed 30-turn trials; 0/10 solved.
  All remained in Reasoner retrieval and never exercised the new tools.
- `easy_fatem_020_t0` through `t6`: seven completed 30-turn trials; kernel
  rescoring finds 2/7 solved. `show_goals` was selected once in `t1` and
  `try_tactic` once in `t5`; neither of those trials solved.
- `easy_fatem_020_t7`: interrupted when a stale background runner was stopped;
  preserve as partial evidence, not a completed denominator.
- `200_turns/easy_fatem_019_t0`: completed unsolved Reasoner-only diagnostic.
- `200_turns/easy_fatem_019_t1`: interrupted by the Qwen thinking/prefill
  provider incompatibility; preserve as provider-failure evidence.

No missing `t8` or `t9` files are implied to exist for `easy_fatem_020`.
