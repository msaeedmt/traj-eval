# Qwen Medium Subgoal Experiment

## Research Question

Can bounded subgoal planning, compiler-triggered reasoner recovery, and strict
critic gates produce useful non-linear communication on medium Lean tasks?

This experiment follows the NLP Lab proposal objectives and the analysis rules
in `docs/LEAN_FAILURE_ANALYSIS_GUIDE.md`:

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

## Command

```powershell
python scripts\run_batch.py `
  --difficulty medium `
  --task-id medium_leancat_008 medium_fateh_001 `
  --trials 10 `
  --setup tool_routed_subgoals_v1 `
  --output-dir data\experiments\qwen_medium_subgoals_v1 `
  --max-turns 100 `
  --max-engineer-failures 3 `
  --max-forced-replans 3 `
  --worker-model <provider-qwen-model> `
  --reasoner-max-tokens 2048 `
  --engineer-max-tokens 4096 `
  --critic-max-tokens 2048 `
  --worker-thinking disabled `
  --outer-orchestrator codex_ultra `
  --skip-existing
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
