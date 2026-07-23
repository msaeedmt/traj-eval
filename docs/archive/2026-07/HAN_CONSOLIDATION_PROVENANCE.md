# Han Consolidation Provenance and Evidence Status

This document records the scientific and Git boundaries of the consolidated
personal `Han` experiment branch. It is a status record, not a claim that every
planned repository-cleanup phase is complete.

## Git provenance

- Clean `Han` starting tip: `360b523f126caef72eb74c94c44e61a279bc1691`.
- Merged `Han-experiment` tip: `0003329d137a08cfcb59fc3d99d8bb5b973d8a42`.
- Merged `experiment/qwen-tool-routed-subgoals` tip:
  `1e2f03b47682dc3216a17d117d13b5facf7a431a`.
- Both source histories are retained as merge parents. After consolidation,
  their superseded tips are to be preserved as the annotated tags
  `archive/Han-experiment` and `archive/qwen-tool-routed-subgoals`; they are not
  additional active branches.
- `main`, `lean-anchors`, and `han-lean-anchors-merge` are outside this
  consolidation and remain unchanged. Promotion from `Han` to the integration
  branch is separately gated by teammate discussion and explicit approval. The
  fifth goal-tool integration setup is therefore not a supported `Han` setup.

## Supported personal experiment setups

The supported setup registry contains exactly four isolated arms:

1. `recovery_triangle_v1` — marker-routed recovery baseline.
2. `recovery_triangle_no_retrieval_v1` — matched retrieval-disabled ablation.
3. `recovery_triangle_stall_handoff_v1` — bounded structured stall handoff.
4. `tool_routed_subgoals_v1` — typed post-tool routing and subgoal ledger.

Baseline and typed-subgoal run bundles retain unsuffixed trace and summary
names. Retrieval and stall ablation arms use setup suffixes. Execution, resume
validation, rescoring, and trace exploration share the same path constructor
and verify both terminal state and trial/setup identity.

## Evidence status and claim boundaries

### Qwen medium typed-subgoal pilot

The 20 raw traces are under `data/batch/qwen_medium_subgoals_v1/`, the derived
summary is under `data/analysis/qwen_medium_subgoals_v1/`, and the narrative
summary is under `docs/experiments/qwen_medium_subgoals_v1/`. All 20 recorded
outcomes are unsolved, with zero independently verified final proofs. The
bundle also records 102 tool handoffs, 12 forced recoveries, and 15 accepted
subgoals. Its recorded decision is `revise_subgoal_strategy`.

These are descriptive run facts and meaningful negative evidence under the
tested conditions, not a success claim. They show that the instrumentation
captured routing and recovery events; they do not validate O1 localization,
O2 detector precision/recall/F1, or any O3 architecture-improvement claim.

### V4 routing ablation

`data/batch/version_4_routing_ablation/shell_runs/v4_20260717_181632/` retains
a completed two-task smoke bundle. Its derived comparison is under
`data/analysis/version_4_routing_ablation/`, and its narrative results are under
`docs/experiments/version_4_routing_ablation/`. It was produced at commit
`41cc85f3cc87aa99c9ba81eb345d0ee0f15f69fa`, before the structured
stall-handoff implementation. The official V4 experiment was not run. The
retained smoke is descriptive instrumentation evidence, not validation of
`recovery_triangle_stall_handoff_v1` or an architecture comparison.

Incomplete V4 material was excluded from scientific claims and copied to the
external recovery archive before its original files were moved to the Windows
Recycle Bin.

### Earlier evidence and integration evidence

- The meeting report and dashboard are retained under
  `docs/lean_easy_failure_report/`.
- The separately approved 100-file V1 relocation is complete. Its raw traces
  are under `data/batch/version_1_trial_traces/`; the relocation preserved each
  file's bytes at the time of the move. Two traces later received the separately
  approved machine-local path-token sanitization recorded in the external
  recovery audit; their schema, sequence, causal, and scientific fields were
  unchanged.
- V2/V3 traces and the V1–V3 failure-mode analysis remain integration-branch
  material. Any later port remains subject to the separate integration gate.

### Presentation evidence

Five sanitized PPTX versions are retained under
`docs/presentations/traj-eval-10min/versions/`, with matching inspection records
under `data/analysis/presentations/traj-eval-10min/`. The promoted decks were
rendered and compared slide-by-slide with their source versions; all 35 rendered
slides were pixel-identical after note-path sanitization.

## Recovery and schema guarantees

- External recovery records retain the bundle, manifest, hashes, original
  paths, source-branch tips, and stash-reachable commits. Those machine-local
  recovery details are intentionally not published here.
- Secret-bearing environment files are neither read nor tracked.
- The trace schema remains version `0.2.0`. Evidence relocation does not change
  scientific fields; approved public sanitization may replace only
  machine-local path tokens, with the exact transformations recorded in the
  external recovery records.
