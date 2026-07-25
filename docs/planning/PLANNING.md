# Two-Week Plan: Lean Rerun, Failure Analysis, and Tooling Review

**Planning date:** July 23, 2026
**Working branch:** `Han`
**Purpose:** produce reproducible evidence about the current Lean workflow,
make the subgoal-tool work presentable, and prepare a short methods review of
Codex and Claude Code.

## Scope and branch boundary

- Do all experiments, analysis, and documentation work on `Han`.
- Do not modify `lean-anchors`.
- Do not promote anything to `han-lean-anchors-merge` until the changes have
  been discussed with teammates and explicitly approved.
- The reasoning agents are Reasoner, Engineer, and Critic. Tool execution is
  performed mechanically by the runtime and is not an agent role.
- Keep API credentials and local provider configuration outside Git.

## This week: Lean rerun and failure evidence

### 1. Lock the rerun design before running it

Rerun the faithful Lean-anchor workflow on the existing easy and medium task
cohorts through an API/provider route different from Shivam's.

Before the full cohort:

- record the task IDs, trial count, model name, provider route, token/turn
  budgets, prompts, tool set, and randomisation settings;
- run one easy and one medium smoke trial to confirm provider reachability,
  trace creation, and independent Lean verification;
- store a non-secret provider probe result with the cohort metadata;
- keep the easy and medium cohorts separate throughout analysis.

The target is the existing 100 easy and 20 medium trials when budget and the
baseline definition allow it. If a smaller slice is necessary, pre-register
the exact task IDs and trial count before looking at outcomes.

Changing the API route can make the rerun a useful replication or robustness
check. It is not, by itself, evidence that one model, provider, or workflow is
better. Any comparison claim requires matched tasks, model settings, budgets,
and verification rules; otherwise the report must label the difference as a
confound.

### 2. Preserve the evidence chain

For every trial, keep:

```text
task definition -> run configuration -> ordered trace -> Lean tool results
-> independent kernel check -> outcome label -> failure review
```

Classify a provider outage, malformed artifact, missing trace, or incomplete
run as a tooling or evidence failure, not as an agent reasoning failure.
Kernel-valid proof closure with no `sorry` or `admit` remains the Lean
correctness gate.

### 3. Produce basic statistics and a renewed failure analysis

Report easy and medium cohorts separately. At minimum, calculate:

- scheduled, started, terminal, and independently verified trial counts;
- kernel-verified proof rate, with a 95% confidence interval where meaningful;
- unsolved, tooling-invalid, and validation-unknown counts;
- silent-failure count, including changed-statement or wrong-target cases;
- Critic proof-check coverage and accept-without-check count;
- retry/probe count, retry-success rate, and repeated-probe or loop count;
- first failed anchor or first decisive failed event, when the trace supports
  localisation;
- reviewed failure-mode counts with denominators and links to representative
  JSONL traces.

Use paired statistics only for genuinely matched before/after tasks. Do not
make a configuration-level improvement claim from unmatched easy-versus-medium
cohorts or from a provider change alone.

### 4. Prepare the failure presentation

Create a compact evidence-first readout for the rerun:

1. cohort and provider provenance;
2. Lean correctness and completion summary;
3. failure table with count, denominator, first event, and independent check;
4. one or two representative trace walkthroughs;
5. what is observed, what is only a hypothesis, and the next decisive test.

Every highlighted failure must retain its exact trace ID and independently
checkable evidence. The presentation should explain failures rather than
equate a dashboard, artifact, or passing wrapper with a scientific result.

## Next week: code cleanup and methods presentation

### 5. Make the subgoal-tool work presentable

Clean the subgoal-tool implementation without changing its claimed scientific
result. The completed medium cohort currently demonstrates observable routing,
subgoal-level localisation, and strict rejection; it does not demonstrate a
kernel-valid medium-task solve or architecture superiority.

The cleanup checklist is:

- identify the active path and isolate experiment-only code from reusable
  Lean infrastructure;
- remove only dead code introduced by the cleanup;
- make configuration, outputs, and rerun commands easy to find;
- keep trace, subgoal, compiler, and critic evidence linked in the summary;
- add or update focused tests for the preserved behaviour;
- prepare a short README-style explanation and one reproducible command.

### 6. Research Codex and Claude Code methods

Use official documentation available at the time of the review. Compare the
tools as development methods, not as a benchmark of model intelligence:

- project instructions and repository conventions;
- planning, coding, testing, and verification loops;
- worktree or branch isolation and review workflow;
- tool execution, permissions, and handling of secrets;
- multi-agent or delegation options where available;
- reproducibility, limitations, and the best fit for this project.

The output is a short comparison table plus a recommendation for how each tool
could support the next Traj-Eval iteration. Clearly distinguish documented
capabilities from local observations.

### 7. Present next week

The next presentation should contain three clearly separated parts:

1. Lean rerun evidence and failure analysis;
2. subgoal-tool cleanup and its evidence boundary;
3. Codex and Claude Code workflow comparison.

## Warehouse evidence used for planning

The Science-Work-Flow warehouse was queried before this plan. Its main planning
signals are provider-reachability failures, artifact-contract failures, and
critic/claim-gate mismatches. Because that warehouse is predominantly
STARGAZER-oriented and includes legacy role labels, it is operational context
for preflight and claim discipline, not the Lean baseline for this rerun.

## Completion criteria

By the end of this week:

- the rerun configuration and provider route are recorded without secrets;
- every completed trial has a trace and an independent Lean outcome, or is
  explicitly labelled as technically invalid;
- basic cohort statistics and reviewed failures are ready to present;
- no conclusion exceeds the available matched evidence.

By the end of next week:

- the subgoal-tool code has a clear active path, focused tests, and a
  reproducible explanation;
- the Codex/Claude Code review is source-backed and presentation-ready;
- the presentation distinguishes engineering status, scientific evidence, and
  open questions.

## Open decisions before execution

- Which exact API/provider route replaces Shivam's route?
- Is the model held constant, or is this explicitly a provider-and-model
  replication rather than a matched comparison?
- Can the full 100-easy and 20-medium cohort be afforded this week?
- Which teammate review date gates any later promotion from `Han` to the merge
  branch?
