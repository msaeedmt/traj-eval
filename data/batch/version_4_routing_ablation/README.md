# Han V4 Lean Routing Ablation

Status: harness and test gates passed. One completed two-task by four-arm
Qwen smoke bundle is retained; the official 160-trial study has not run.

This historical V4 study, now retained on `Han`, asks whether routing policy
changes recovery on two weak V1 tasks without changing the mathematical
workers or their tools. The historical V1 evidence reports
`easy_fatem_019` at 0/10 solved and `easy_fatem_020` at 3/10 solved.

## Fixed substrate

- Tasks: `easy_fatem_019`, `easy_fatem_020`.
- Model: one explicitly selected Qwen OpenAI-compatible backend for every role.
- Worker roles: Reasoner (the Lean planner-equivalent), Engineer, Critic.
- Tools: `check_lean`, `search_lemmas`, `try_tactic`, `show_goals`.
- Kernel tools: source/tests recorded at
  `han-lean-anchors-merge@45f0ab1`; this is provenance, not a promotion
  instruction.
- Imports: `import Mathlib`.
- Worker output cap: 1,500 tokens; controller output cap: 128 tokens.
- Maximum worker turns: 200.
- Real Lean 4.30 `--stdin` verification and the same offline validator.
- Twenty trials per task and arm; no outcome-based early stopping.

## Intervention

Only speaker selection changes:

1. `legacy_deterministic`: fixed Reasoner → Engineer → Critic repair loop.
2. `upstream_free`: the `lean-anchors` handoff-marker policy from `74f275e`,
   ported onto the fixed workers and worker-turn accounting.
3. `central_worker_matched`: Qwen controller calls are additional to 200 worker
   calls.
4. `central_total_call_matched`: Qwen controller and worker calls share a
   200-call cap.

The worker-matched and total-call-matched controller arms separate the possible
benefit of controller decisions from the benefit of simply spending more model
calls.

## Stuck-recovery gate

Two controller-only smoke probes are excluded from the 160-trial denominator:

- repeated Reasoner retrieval/unchanged planning must route to Engineer;
- repeated Engineer proof/compile failure without a viable strategy must route
  to Reasoner.

A local Engineer syntax repair is tested offline and must stay with Engineer.
The full trials also count evidence-backed Reasoner→Engineer recovery,
Engineer→Reasoner replanning, and Engineer-local retries.

## Run order and evidence safety

1. Local Python and real Lean tool gates.
2. Two controller-only Qwen stuck probes.
3. Eight full-arm smoke trials (two tasks × four arms × one trial).
4. The balanced 160-trial run.

The runner refuses to overwrite artifacts. An infrastructure failure remains in
its original JSONL and receives at most one `_retry1.jsonl`; an agent failure is
never retried. Generated `RESULTS.md`, `summary.json`, and `run_manifest.json`
are written only after the selected run completes.

The 100 V1 JSONL files are retained under
`data/batch/version_1_trial_traces/`. New raw, analysis, and human-readable
outputs are separated under `data/batch/`, `data/analysis/`, and
`docs/experiments/`.

Provider credentials and endpoint are read without modification from the file
named by `TRAJ_EVAL_PROVIDER_ENV` (the CLI override is equivalent). They are
passed directly into the in-memory AG2 configuration; the runner sets only
`TRAJ_EVAL_MODEL` in its process environment and never edits the provider file.

## Claim boundary

The retained smoke bundle is descriptive pilot evidence about routing burden,
kernel-validated outcomes, calls, latency, tool failure, and coordination on
two selected tasks. It does not establish a recovery effect, architecture
improvement, or proposal-wide result.
