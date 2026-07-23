# Legacy Deterministic Routing

The host selects the fixed sequence Reasoner → Engineer → Critic. A Critic
rejection returns to Engineer. This is the Lean three-role mapping of the
deterministic topology introduced by `c961421` (Reasoner replaces its Planner;
kernel-backed validation replaces its simulated terminal Executor). The
capitalized legacy roles in that sentence describe historical compatibility
code, not the current three-reasoning-agent setup. Workers do not choose
handoffs and no routing model call is made.

The pre-registered official design assigns 20 trials per selected task to this
arm; that official run has not been executed. Raw traces stay under this arm's
`data/batch/` directory, machine-readable summaries belong under
`data/analysis/version_4_routing_ablation/`, and reader-facing `RESULTS.md`
belongs under `docs/experiments/version_4_routing_ablation/`. Retained smoke
observations are descriptive only.
