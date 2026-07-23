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

This arm receives 20 trials for each selected task. `RESULTS.md` and
`summary.json` are generated only after completion and are never overwritten.
