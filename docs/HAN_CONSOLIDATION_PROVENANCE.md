# Han Consolidation Provenance and Evidence Status

This document records the scientific and Git boundaries of the consolidated
personal `Han` experiment branch. It is a status record, not a claim that every
planned repository-cleanup phase is complete.

## Git provenance

- Clean `Han` starting tip: `360b523f126caef72eb74c94c44e61a279bc1691`.
- Merged `Han-experiment` tip: `0003329d137a08cfcb59fc3d99d8bb5b973d8a42`.
- Merged `experiment/qwen-tool-routed-subgoals` tip:
  `1e2f03b47682dc3216a17d117d13b5facf7a431a`.
- Both source histories are retained as merge parents. Their planned
  `archive/*` ref names are a separate ref-cleanup phase.
- `main`, `lean-anchors`, and `han-lean-anchors-merge` are outside this
  consolidation. In particular, the fifth goal-tool integration setup belongs
  only on the future integration branch and is not a supported `Han` setup.

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

`data/experiments/qwen_medium_subgoals_v1/` is a complete 20/20-trial bundle.
All 20 outcomes are unsolved. The run nevertheless contains useful negative
evidence: 102 tool handoffs, 12 forced recoveries, 15 accepted subgoals, and
zero verified completions. Its recorded decision is
`revise_subgoal_strategy`.

This is meaningful O1/O2 observability and recovery evidence. It is not a
success claim and does not support an O3 architecture-improvement claim.

### V4 routing ablation

`data/batch/version_4_routing_ablation/shell_runs/v4_20260717_181632/` is the
retained completed two-task smoke bundle. It was produced at commit
`41cc85f3cc87aa99c9ba81eb345d0ee0f15f69fa`, before the structured
stall-handoff implementation. It is baseline routing-ablation evidence, not
validation of `recovery_triangle_stall_handoff_v1`.

Incomplete V4 material was excluded from scientific claims and copied to the
private recovery archive before its original files were moved to the Windows
Recycle Bin.

### Earlier evidence and integration evidence

- The meeting report and dashboard are retained under
  `docs/lean_easy_failure_report/`.
- Promotion of the 100-file V1 raw-trace set into its final versioned
  `data/batch/` location remains a separately approved mass move. Until then,
  the generated meeting artifacts are preserved, but a clean-worktree rebuild
  still depends on that pending source promotion.
- V2/V3 traces and the V1–V3 failure-mode analysis remain integration-branch
  material and will be ported only when the frozen integration worktree is
  released for the separately planned rebuild.

### Presentation evidence

Five sanitized PPTX versions are retained under
`docs/presentations/traj-eval-10min/versions/`, with matching inspection records
under `data/analysis/presentations/traj-eval-10min/`. The promoted decks were
rendered and compared slide-by-slide with their source versions; all 35 rendered
slides were pixel-identical after note-path sanitization.

## Recovery and schema guarantees

- The private recovery bundle covers all branch and stash-reachable commits.
- Recovery manifest SHA-256:
  `43C6B66FD038A296F191E12A21CAEE091E685A2F27474A0E488882B5D6CA62D3`.
- Git bundle SHA-256:
  `9FB33E97A66753CFA151E5FC4C888C8627629DD98917B56D0866386A0B95E3C8`.
- Secret-bearing environment files are neither read nor tracked.
- Historical trace event content is not rewritten. The trace schema remains
  version `0.2.0`; only path registries and derived artifact locations are
  normalized.
