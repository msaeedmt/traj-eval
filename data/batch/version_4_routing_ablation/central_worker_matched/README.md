# Central Controller: Worker-Matched

A separate Qwen routing-only controller selects Reasoner, Engineer, or Critic.
It has no tools and may not solve, write Lean, or declare success. The workers
retain the same maximum 200 turns as the non-controller arms; controller calls
are additional and reported separately.

The controller is designed to recover a repeated Reasoner retrieval loop by
routing to Engineer and a repeated strategic Engineer failure by routing back
to Reasoner. Local syntax/elaboration repair stays with Engineer.

The pre-registered official design assigns 20 trials per selected task to this
arm; that official run has not been executed. Raw traces stay under this arm's
`data/batch/` directory, machine-readable summaries belong under
`data/analysis/version_4_routing_ablation/`, and reader-facing `RESULTS.md`
belongs under `docs/experiments/version_4_routing_ablation/`. Retained smoke
observations are descriptive only.
