# Central Controller: Worker-Matched

A separate Qwen routing-only controller selects Reasoner, Engineer, or Critic.
It has no tools and may not solve, write Lean, or declare success. The workers
retain the same maximum 200 turns as the non-controller arms; controller calls
are additional and reported separately.

The controller must recover a repeated Reasoner/planner retrieval loop by
routing to Engineer and a repeated strategic Engineer failure by routing back
to Reasoner. Local syntax/elaboration repair stays with Engineer.

This arm tests controller usefulness when worker opportunity is held fixed, but
it spends more total model calls. It receives 20 trials for each selected task.
`RESULTS.md` and `summary.json` are generated only after completion and are
never overwritten.
