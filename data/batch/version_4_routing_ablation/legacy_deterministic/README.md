# Legacy Deterministic Routing

The host selects the fixed sequence Reasoner → Engineer → Critic. A Critic
rejection returns to Engineer. Workers do not choose handoffs and no routing
model call is made.

Everything else is fixed to the V4 common substrate described in the parent
README. This arm receives 20 trials for each selected task. `RESULTS.md` and
`summary.json` are generated only after completion and are never overwritten.
