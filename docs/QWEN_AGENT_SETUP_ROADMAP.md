# Qwen Communication-First Agent Roadmap

## Research Question

Can agent-chosen, evidence-backed recovery routes make Qwen revise failed Lean
strategies without merely adding chatter, loops, or critic masking?

This question is grounded in the NLP Lab proposal:

- O1: localize the first failed event and originating role.
- O2: classify coordination collapse, perseveration, critic masking, and
  productive revision.
- O3: compare architectures only after matched repeated trials. The 10-task
  pilot does not support an O3 claim.

The design also follows the repository's modern-agent learning rule: preserve
the current system as evidence, add one intervention at a time, and prefer
verifier feedback over a larger agent cast.

## Evidence Used

### Lean baseline

The 100 existing easy-task traces are mostly linear. They contain 96 explicit
reasoner-to-engineer handoffs, 59 engineer-to-critic handoffs, and zero explicit
engineer-to-reasoner or critic-to-engineer handoffs. A role transition alone is
not communication: three engineer-to-reasoner transitions came from runtime
fallbacks and carried no `handoff_target` evidence.

### Science-Work-Flow warehouse

The broader Qwen history is not a matched Lean comparison, but it identifies
the risks the pilot should expose: format fragility, premature convergence,
perseveration/reasoning loops, environment-tool failures, and critic masking.
Provider health is mixed, so every live run requires a redacted preflight.

## Experimental Contract

Communication is the primary pilot outcome, but more messages are not success.

An evidence-backed revision is a causal path in `build_graph(events)` from a
failed `check_lean` result to an explicit engineer-to-reasoner handoff, or an
explicit critic rejection sent to the engineer. A productive recovery requires
that revision to reach a later successful compile and a kernel-valid final
proof. Runtime fallback routes are reported separately.

In the A2 marker setup, the runtime validates an expressed target, executes a
tool, returns its result, and stops a stuck run; Qwen owns every semantic route.
The focused E1 setup tests one stronger mechanism: after three failed proof
compiles on one subgoal, the runtime visibly routes back to the reasoner. The
runtime chooses only the recovery role, not the revised mathematical strategy.

## Agent Setup Ladder

| ID | Setup | Hypothesis | Gate |
| --- | --- | --- | --- |
| A0 | Single-agent ReAct | Proposal control for multi-agent claims | Required before O3 comparison |
| A1 | Historical linear multi-agent | Existing 100-trace control | Frozen; do not rerun in place |
| A2 | `recovery_triangle_v1` | Existing roles can use compiler evidence to replan | Current 10-task pilot |
| A3 | On-demand strategy critic | Fresh-context critique helps when A2 never reroutes | Only if eligible A2 failures have zero evidence-backed revisions |
| A4 | Dual isolated engineers | Independent proof attempts improve diversity | Only with equal total token/tool budget |
| A5 | Verified fact memory | Compiler-approved lemmas help compound tasks | Multi-theorem work only |
| E1 | `tool_routed_subgoals_v1` | Bounded forced replanning and per-subgoal critic gates can produce observable non-linear recovery | Three FATEM115 feasibility trials only |

The completed A2 routing surface is deliberately small:

```text
reasoner -> engineer
engineer -> check_lean/search_lemmas -> engineer
engineer -> reasoner | critic
critic -> check_lean -> critic
critic -> engineer | APPROVE
```

E1 uses registered tools rather than text markers:

```text
reasoner -> plan_subgoal/read_subgoals/route_next_agent
engineer -> check_lean/submit_subgoal/route_next_agent
critic -> review_lean/review_subgoal/finish_run/route_next_agent
third failed proof compile -> reasoner (runtime-enforced and trace-labelled)
```

The subgoal state is a trial-local DAG with at most six nodes. A valid plan has
at least two independent leaf nodes and one integration node. A critic can
accept a subgoal only after independently compiling the exact submitted hash;
the run finishes only when every node is accepted and the final dependency
cone covers every other node.

## FrenzyMath Adoption

FrenzyMath projects are adapters and external baselines, not code to merge into
the current runtime.

- [Archon](https://github.com/frenzymath/Archon): source of design principles
  for bounded DAG planning and visible state updates. E1 adapts those principles
  locally; it copies no Archon code and adds no Archon dependency.
- [Danus](https://github.com/frenzymath/Danus): source for the later rule that
  only verifier-approved facts enter shared memory.
- [Rethlas](https://github.com/frenzymath/Rethlas): generator-verifier reference,
  evaluated separately from kernel-checked Lean runs.
- [LeanSearch](https://github.com/frenzymath/LeanSearch): already represented by
  the current remote `search_lemmas`; do not add its PostgreSQL/vector stack
  while search overuse is unresolved.
- [jixia](https://github.com/frenzymath/jixia): possible read-only declaration,
  reference, elaboration, and proof-state adapter after exact Lean `v4.30.0`
  compatibility is verified.
- [Reap](https://github.com/frenzymath/reap): separate neural-tactic arm that
  requires endpoint, privacy, version, and budget approval.

Do not change roles and tools in the same comparison. After A2, test a role
change or a tool change, never both at once.

E1 intentionally changes routing, state, and review gates together. It is
therefore a mechanism-feasibility study, not a causal architecture comparison.
Its traces can support O1 localization and O2 taxonomy refinement, but cannot
support O3 improvement claims.

## Pilot Output

The ignored output directory is:

```text
data/experiments/qwen_recovery_triangle_v1/
  <task_id>_t0.jsonl
  summary.json
  summary.md
```

`TrialMeta` records setup, prompt revision, routing policy, tools, model, and
turn cap. The raw trace schema remains `0.2.0` and old traces remain readable.

The E1 ignored output directory is:

```text
data/experiments/qwen_tool_routed_subgoals_v1/
  easy_fatem_115_t0.jsonl
  easy_fatem_115_t1.jsonl
  easy_fatem_115_t2.jsonl
  summary.json
  summary.md
```

E1 is bounded to 80 routing decisions, three consecutive failed proof compiles
before forced reasoner recovery, and two forced replans per trial. Existing
`data/batch` and A2 traces are read-only experiment history.

## Decision Rule

- No failed-compile opportunities: pilot is inconclusive.
- Eligible failures but no evidence-backed rerouting: advance to A3.
- Rerouting occurs but never makes progress: improve prompt/tool evidence before
  adding an agent.
- At least one productive recovery: scale A2 to 10 trials per task.
- Claim architecture improvement only after a matched 10 x 10 comparison,
  single-agent control, paired bootstrap, and effect-size reporting.

For E1, first ask whether Qwen adopts the routing tools, defines and reviews
subgoals, revises after forced recovery, and reaches a verifier-backed finish.
Solve rate is descriptive because the three trials are unmatched and target a
single previously unsolved task.

## A2 Pilot Result

The 2026-07-09/10 pilot ran one live Qwen trial per easy task and then rescored
all ten local traces with the Lean validator. Results:

- 10/10 traces completed: 6 solved, 2 silent failures, and 2 unsolved.
- Four trials exposed 14 failed compiler results.
- Qwen made 17 explicit handoffs: 9 reasoner-to-engineer and 8
  engineer-to-critic.
- It made zero engineer-to-reasoner and zero critic-to-engineer handoffs.
- One reasoner stalled in a search loop before handing off.
- Two critics approved artifacts that failed offline validation.

The deterministic gate therefore selects A3, `on_demand_strategy_critic`, as
the next experiment. This is O1/O2 pilot evidence only; O3 remains unclaimed.
The local evidence is in
`data/experiments/qwen_recovery_triangle_v1/summary.json`.

## E1 Focused Pilot Result

E1 ran three live Qwen trials on `easy_fatem_115` with 80 routing decisions,
three failed proof compiles per forced recovery, and at most two forced
replans. This analysis is grounded in the NLP Lab proposal, the role/global
analysis contract in `docs/LEAN_FAILURE_ANALYSIS_GUIDE.md`, and the typed-
evidence authority model in `docs/HAN_LEAN_ANCHOR_MERGE.md`.

| Trial | Recovery behavior | Critic behavior | Offline outcome |
| --- | --- | --- | --- |
| t0 | One forced reasoner return; no strategy revision | Never reached critic | Unsolved |
| t1 | Two forced returns; two revisions; later compile success | Exact-hash mismatch, rejection, critic-to-engineer repair; turn cap | Unsolved |
| t2 | One forced return; one revision; three submitted subgoals | Three exact-byte compile approvals and runtime finish | Silent failure |

Across the three trials, Qwen produced 19 tool handoffs, four forced
recoveries, three recorded strategy revisions, 15 failed compiler results, 14
successful compiler/reviewer results, one critic rejection, and three accepted
subgoals. There were zero solved trials. One runtime completion was critic
masking because offline statement preservation failed. This is O1/O2 evidence;
it is not an O3 architecture-improvement result.

### Mathematical Diagnosis

The human strategy is short: prove both directions directly and reverse the
two relation hypotheses before applying transitivity. The imported Mathlib
`Transitive` uses implicit element arguments, so the key application supplies
the two proof hypotheses, not explicit `x y z` terms.

Qwen repeatedly treated those implicit arguments as explicit. The first
reasoner revision described the problem incorrectly, and the engineer kept
trying forms such as applying the hypothesis to `z y x`. Search exposed the
right declaration but did not correct the application model. This is a valid
strategy at the mathematical level but an invalid Lean API strategy.

Trial t2 eventually compiled by declaring a new local `def Transitive` with
explicit arguments. That shadowed Mathlib's benchmark symbol. The exact file
compiled and the critic recompiled the same hash, but the proof body failed
when restated under the original imports and statement. Therefore
`final_proof_compiles=true` and `statement_preserved=false` are consistent;
this is not an infrastructure error.

### Graph Diagnosis

The role-transition path became cyclic, but the event causal graphs did not
branch. Their longest paths covered every event: 23/23 edges for t0, 79/79 for
t1, and 74/74 for t2. AG2 still executed one speaker/tool at a time, so each
trace is a serial chain over a branched subgoal-state DAG.

This distinction matters for the proposal. E1 localizes recovery and critic
failure in a graph (O1) and adds useful coordination labels (O2), but it does
not test parallel or branching reasoning. A later branching experiment needs
isolated engineer attempts or explicit multi-parent dependency edges; more
role revisits alone do not create a branching causal graph.

### Implemented Hardening

The post-pilot implementation adds only mechanisms demanded by observed
failures:

- Typed `finish_run` artifacts are recognized only through the full matching-
  hash chain: engineer compile, submission, critic compile, critic accept, and
  finish.
- A final faithfulness gate rechecks compilation, sorry freedom, original
  statement preservation, and axioms before a future runtime may finish.
- `read_candidate` gives the critic the exact submitted bytes, avoiding t1's
  retyping/hash loop.
- JSONL writes flush per event, and future traces end with a causal system
  event recording `clean`, `cap`, `stuck`, or `framework_stop`.

Historical E1 traces are not rewritten. The local evidence remains in
`data/experiments/qwen_tool_routed_subgoals_v1/`; the interrupted observability
audit is preserved separately under its `aborted/` directory.

### Low-Token Specialist Direction

Codex Ultra remains the main engineering/research orchestrator outside the
measured trial. Future trial roles should use the configured lower-cost model
with explicit response budgets, recorded in `TrialMeta`:

```text
reasoner: short strategy/revision budget
engineer: moderate proof/tool budget
critic: short evidence-review budget
executor and gates: deterministic, zero LLM tokens
```

Do not switch provider models silently. A matched budget experiment should add
role token caps as its single intervention, retain the same task and runtime,
and compare completion, useful revision, gate denial, and kernel-valid solve
rates. Compact state deltas should replace repeated full snapshots before
persistent memory is considered.

### Growth Gate

Do not scale E1 to 10 x 10 yet. First run a small E1.1 replay with the final
faithfulness gate and exact-candidate review, then require at least one
kernel-valid solve without critic masking. Only then compare a low-token role
budget or a genuinely branching engineer setup. O3 still requires matched
repeated trials, a single-agent control, paired uncertainty, and effect sizes.

Modern persistent memory, dynamic skill loading, arXiv/web search, and book
retrieval remain deferred. They are separate interventions with provenance and
data-governance requirements. Any API-backed change to stored history requires
explicit user authorization, and only verifier-approved facts may enter future
shared proof memory.
