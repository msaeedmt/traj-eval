# Upstream Free Routing

Workers select the next role with the handoff-marker graph copied from the
`lean-anchors` policy at commit `74f275e`:

- Reasoner → Engineer
- Engineer → Reasoner or Critic
- Critic → Engineer or terminal approval
- a tool result returns to its caller

The routing algorithm retains the upstream invalid-handoff fallback and stuck
guards. Its cap is expressed as 200 worker turns so the useful worker budget is
matched to the other arms; worker prompts and tools are the V4 common substrate,
not the upstream branch's wholesale runner.

The pre-registered official design assigns 20 trials per selected task to this
arm; that official run has not been executed. Raw traces stay under this arm's
`data/batch/` directory, machine-readable summaries belong under
`data/analysis/version_4_routing_ablation/`, and reader-facing `RESULTS.md`
belongs under `docs/experiments/version_4_routing_ablation/`. Retained smoke
observations are descriptive only.
