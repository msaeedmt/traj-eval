# Han / Lean Anchor Research Record

> **Archived historical record.** This document preserves the boundary and
> evidence interpretation used during the July 2026 consolidation. Current
> product and branch policy is defined by `CODEX.md` and
> `docs/idea/concept.md`.

This document is the sanitized research record for the personal `Han` branch.
It explains which work is active Lean infrastructure, which work is a personal
experiment, and what the available evidence can and cannot support. It contains
no raw chat bodies, credentials, personal material, or copied tool transcripts.

## Branch and repository boundary

| Surface | Research role |
|---|---|
| `Han` | Personal experiments, sanitized results, and educational interpretation |
| `archive/qwen-tool-routed-subgoals` | Planned annotated tag preserving the superseded tool-routed source tip |
| `han-lean-anchors-merge` | Separately gated integration branch; no promotion without teammate discussion and explicit approval |
| External historical archive | Read-only recovery and historical experiment source outside the public repository |

"Pure Lean" described the integration snapshot at the time of this archived
analysis, not rewritten history. The copied Lean integration at `e491473`
remains essential. It is a Windows-clean integration snapshot, not a merge
commit, and must not be reverted as cleanup.

The current reasoning-agent model has exactly three roles: Reasoner, Engineer,
and Critic. Historical Planner and Executor/Repairer labels are compatibility
labels; tool execution is performed by a non-agent runtime.

## Research coverage

The pre-consolidation audit deduplicated exact working-directory task IDs and
reviewed 73 locally discoverable Codex histories: 33 for this repository and 40
from an external historical archive. It recorded no missing task in the
canonical local rollout inventory available at that time. Only aggregate
decisions and findings are recorded here.

The external historical archive was queried read-only. Its history illustrates
why provider reachability, model output, physical artifacts, critic opinions,
and external validation must be reported separately. It includes provider
failures, template-like outputs, artifact mismatches, coordination collapse,
and critic masking. Those runs are diagnostic context; they are not a matched
Lean retrieval study and do not prove that a larger runtime improves Lean or
the overall NLP proposal.

## How the work evolved

| Commit | What it established | Evidence boundary |
|---|---|---|
| `9b3db45` | Initial Qwen JSONL Engineer worker | A task-specific action worker, not a general architecture result |
| `74ecd5d` | Stargazer Engineer evidence | Actions could be emitted, executed, written, and traced |
| `1414edf` | Engineer moved under `agents` | Preserved historical implementation layout |
| `e491473` | Lean anchors copied into the integration line | Essential Lean integration; not a merge to undo |
| `8932864` | Integration boundary documented | Documentation, not causal evidence |
| `eb3fb46` | Generic contracts/orchestrator compatibility work | Did not break Lean tests; did not improve the active Lean path |
| `793d238` | Dataset verifier restored | Retention depends on real/corrupt fixture behavior |
| `24934af` to `205e114` | Lean failure traces, outcome semantics, and analysis | Improved diagnosis and external-verdict reporting |
| `88f9da0` | Free-routing communication experiment | Prompt/routing evidence, not a runtime benefit |
| `3722de5` | Recovery and faithfulness pilot | Caught statement shadowing and serial recovery; no solved-task gain |

The read-only tool-routed branch extends this evidence, but its experiments are
not silently mixed into the public cleanup claim.

## Matched retrieval intervention on `Han`

`recovery_triangle_no_retrieval_v1` is a personal ablation setup. Relative to
`recovery_triangle_v1`, it keeps the same roles, prompts, routing policy,
provider route, tool names, and turn budget. It changes only the result of
`search_lemmas` to a deterministic retrieval-disabled response. Trial metadata
records `retrieval_condition`, and the non-baseline arm receives a distinct
trial ID, trace path, and summary filename so artifacts cannot overwrite or
silently mix the two arms.

Tests check that the original setup still receives the original tool mapping,
that the ablated setup preserves the search function's name, documentation, and
signature, and that the two metadata records differ only in the setup and
retrieval-condition labels. Tests also preserve the legacy baseline trace name
while checking that the ablation has a distinct identity and path. The fixed
Lean/routing/communication/analyzer/search
test set passed 78 tests, and the independent provider-registration probe passed.

### Contained Codex smoke

The contained local smoke used `gpt-5.4-mini`, low reasoning, existing ChatGPT
authentication, no fallback, read-only empty worker state, schema-constrained
role output, and a fixed LeanCat002 wrapper. The host retained role order and
Lean validation. Six worker processes were attempted, three per arm.

Both arms are invalid rather than negative results. The local Codex CLI exited
before producing an event or model response because its enabled rollout-budget
configuration required an additional
`features.rollout_budget.reminder_at_remaining_tokens` value. A seventh
read-only diagnostic invocation isolated that startup error. No arm produced an
admissible proof body, so the host placeholder correctly failed Lean. The valid
and invalid compiler fixtures nevertheless confirmed Lean 4.30 `--stdin`
validation independently.

Consequently, this run measured no retrieval effect. It would be incorrect to
report equal failures as evidence that retrieval does not help: neither model
arm actually started. The failure is retained as containment and experimental
instrumentation evidence, not task-performance evidence.

## Engineer component ablation

The Engineer analysis used no extra model calls. Fixed action/result records
were replayed through the current code.

| Gate | Observed result | Interpretation |
|---|---|---|
| skipped `run` followed by `finish` | Classified as verified | False-positive verification |
| successful `run_process` followed by `finish` | Classified as unverified | False-negative verification |
| declared `allowed_paths` | Not enforced by write handlers | Safety contract is descriptive, not authoritative |
| malformed mixed output | Valid actions were partially accepted | A malformed response can have partial effects |
| hidden evaluation | Excluded from step prompts | Correct boundary |
| active Lean import graph | 25 nodes, 59 edges, unchanged; no Engineer edge | Engineer/runtime is dormant for active Lean execution |

These deterministic replay observations identify truthfulness and safety
defects in the tested component and show its dependency burden. They do not
measure broad Engineer task utility. The archived analysis therefore proposed
removing the dormant generic runtime and Engineer package from the integration
surface; it is not current authorization to delete either component from
`Han`.

## Educational conclusion

Strengths of the study are the matched code-level retrieval intervention, an
external Lean kernel verdict, immutable statement wrapper, deterministic
runtime-truthfulness checks, and explicit separation between provider,
artifact, critic, and validator outcomes.

Drawbacks are substantial: one theorem, one model, one attempted trial per arm,
residual Codex wrapper behavior, a local configuration startup failure, and an
Engineer replay that measures correctness rather than general usefulness.

The defensible conclusion is therefore narrow. The evidence establishes dormant
coupling, concrete safety defects, and instrumentation capable of testing a
retrieval effect. This particular smoke did not establish that effect, and it
cannot establish overall NLP-proposal improvement or architectural superiority.
That requires repeated matched trials and a single-agent control after the
contained runner starts successfully.

## Recovery

External recovery records preserve approved source material and the
pre-consolidation branch tips. Cleanup on `Han` is performed as ordinary
commits, and superseded source tips are preserved as annotated `archive/*`
tags. Each cleanup commit can be reversed with a normal `git revert <commit>`.
Promotion to `han-lean-anchors-merge` remains separately gated. Neither branch
history nor `e491473` is rewritten.
