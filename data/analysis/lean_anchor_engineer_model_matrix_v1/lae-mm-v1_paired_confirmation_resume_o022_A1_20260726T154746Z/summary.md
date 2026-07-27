# Lean Recovery Triangle Run

- Setup: `recovery_triangle_v1`
- Model: `openai/gpt-5.4-2026-03-05`
- Completed: 144/190
- Provider status: `partial_or_failed`
- Decision: `scale_recovery_triangle_to_10_trials`

## Outcomes

- silent_failure: 27
- solved: 79
- unsolved: 38

## Communication

- Explicit handoffs: 272
- Engineer to reasoner: 10
- Critic to engineer: 0
- Eligible recovery trials: 81
- Evidence-backed revision trials: 10
- Productive recovery trials: 1
- Implicit/fallback reasoner reentries: 0
- Engineer-local repair trials: 52
- Reasoner stall trials: 0
- Critic masking trials: 27

## Proposal Interpretation

This run tests O1/O2 observability of agent-chosen recovery routes.
It does not support an O3 architecture-improvement claim.
