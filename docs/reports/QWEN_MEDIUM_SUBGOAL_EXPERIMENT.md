# Qwen Medium Subgoal Experiment

## Research Question

Can bounded subgoal planning, compiler-triggered reasoner recovery, and strict
critic gates produce useful non-linear communication on medium Lean tasks?

This experiment follows the NLP Lab proposal objectives and the analysis rules
in `docs/guides/LEAN_FAILURE_ANALYSIS_GUIDE.md`:

- O1: localize the first failed or recovered subgoal in the causal trace.
- O2: classify reasoner, engineer, critic, and global coordination failures.
- O3: not claimed. This is an unmatched mechanism study, not an architecture
  comparison.

## Orchestration Contract

Codex Ultra is the external research orchestrator. It chooses and launches the
fixed experiment, checks completion, and analyzes the resulting JSON. It does
not speak inside a measured AG2 trial.

The measured workers use one explicitly recorded low-cost Qwen model:

```text
reasoner: 2048 output tokens
engineer: 4096 output tokens
critic: 2048 output tokens
Lean compiler and validation gates: deterministic, zero LLM tokens
```

AG2 speaker selection is deterministic plumbing around agent tool choices; it
does not call an LLM controller. Every trace records
`outer_orchestrator`, `worker_models`, `role_max_tokens`, and
`controller_uses_llm=false` in `TrialMeta.config`.

## Pre-Registered Slice

Run the first metadata-listed task from each available medium source stratum:

| Task | Source | Trials |
| --- | --- | ---: |
| `medium_leancat_008` | LeanCat | 10 |
| `medium_fateh_001` | FATE-H | 10 |

The selection is fixed before seeing outcomes. It is a 20-trial feasibility
slice, not a representative estimate over all medium tasks.

## Plan And Trace Contract

Each raw JSONL remains one `TrialMeta` followed by ordered `TraceEvent` rows.
Before termination, the deterministic controller appends a `controller_plan`
system event containing:

- reasoner ownership and deterministic persistence authority;
- every accepted plan creation/revision;
- the final subgoal DAG, statuses, attempts, failures, and feedback;
- forced recovery and strategy revision counts.

`summary.json` contains a compact `trace_exploration` row per valid trace with
causal graph counts, role-transition counts, and final controller-plan facts.
No database, API-generated diagnosis, or raw trace schema migration is added.

For medium tasks, the reasoner should use four to six concrete, independently
compilable artifacts. The compiler tool normalizes away agent-supplied imports
and checks every candidate under the dataset task's canonical imports/context.
A successful `purpose="subgoal"` or `purpose="final"` compile atomically submits
that candidate and routes it to the critic, preventing verified work from being
lost to further probes.

## Offline reconstruction command

The retained traces can be rescored without any model call by using
`--summarize-existing`. Derived outputs are write-once, so reconstruction must
target fresh analysis and documentation directories. A missing or invalid trace
is recorded as an incomplete input; it is never replaced by a live trial.

```powershell
python scripts\run_batch.py `
  --difficulty medium `
  --task-id medium_leancat_008 medium_fateh_001 `
  --trials 10 `
  --setup tool_routed_subgoals_v1 `
  --output-dir data\batch\qwen_medium_subgoals_v1 `
  --analysis-dir data\analysis\recomputed\qwen_medium_subgoals_v1 `
  --docs-dir docs\experiments\recomputed\qwen_medium_subgoals_v1 `
  --max-turns 160 `
  --max-engineer-failures 3 `
  --max-forced-replans 3 `
  --worker-model <provider-qwen-model> `
  --reasoner-max-tokens 2048 `
  --engineer-max-tokens 4096 `
  --critic-max-tokens 2048 `
  --worker-thinking disabled `
  --outer-orchestrator codex_ultra `
  --summarize-existing
```

## Reading The Result

First inspect `summary.json`, then follow selected trial IDs into their JSONL
causal events. Compare:

- plan completeness and revision history;
- failed compile to forced recovery to revised plan;
- engineer submission to exact-byte critic review;
- critic rejection/acceptance and final faithfulness validation;
- graph roots/leaves and role transitions;
- solved, unsolved, silent failure, and validation unknown outcomes.

The main success criterion is a kernel-valid solve with an observable,
evidence-backed plan/review chain. More messages or role revisits alone are not
success.

## Completed Run

The committed cohort contains 20 terminal JSONL traces: ten trials each for
`medium_leancat_008` and `medium_fateh_001`. An offline rescore of all 20 traces
produced:

| Measure | Result |
| --- | ---: |
| Solved / unsolved | 0 / 20 |
| Explicit handoffs | 102 |
| Reasoner to engineer | 26 |
| Engineer to reasoner | 19 |
| Critic to engineer | 26 |
| Failed / successful compiler results | 323 / 266 |
| Subgoals accepted | 15 |
| Critic approvals | 0 |
| Verified completions | 0 |

This provides descriptive trajectory and instrumentation evidence relevant to
O1/O2. It does not validate localisation accuracy or detector precision,
recall, or F1. O3 is not tested: there is no matched baseline, stress
progression, or early-prediction model. Following
`docs/guides/LEAN_FAILURE_ANALYSIS_GUIDE.md`, successful probes and accepted subgoals
are not treated as final theorem proofs. Under the tested conditions, typed
routing produced substantial return communication and strict critic rejection
but no kernel-valid medium-task solution.

`data/analysis/qwen_medium_subgoals_v1/summary.json` and
`docs/experiments/qwen_medium_subgoals_v1/summary.md` are deterministic offline
summaries of the raw traces. Infrastructure interruption is represented by a
missing terminal event and is not reclassified as a proof failure; the resume
guard skips only traces containing an explicit terminal event.
