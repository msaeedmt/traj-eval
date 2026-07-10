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

The runtime may validate an expressed target, execute a tool, return its result
to the caller, and stop a stuck run. It must not choose a semantic next agent
because a compile failed; that decision remains with Qwen.

## Agent Setup Ladder

| ID | Setup | Hypothesis | Gate |
| --- | --- | --- | --- |
| A0 | Single-agent ReAct | Proposal control for multi-agent claims | Required before O3 comparison |
| A1 | Historical linear multi-agent | Existing 100-trace control | Frozen; do not rerun in place |
| A2 | `recovery_triangle_v1` | Existing roles can use compiler evidence to replan | Current 10-task pilot |
| A3 | On-demand strategy critic | Fresh-context critique helps when A2 never reroutes | Only if eligible A2 failures have zero evidence-backed revisions |
| A4 | Dual isolated engineers | Independent proof attempts improve diversity | Only with equal total token/tool budget |
| A5 | Verified fact memory | Compiler-approved lemmas help compound tasks | Multi-theorem work only |

The pilot routing surface is deliberately small:

```text
reasoner -> engineer
engineer -> check_lean/search_lemmas -> engineer
engineer -> reasoner | critic
critic -> check_lean -> critic
critic -> engineer | APPROVE
```

## FrenzyMath Adoption

FrenzyMath projects are adapters and external baselines, not code to merge into
the current runtime.

- [Archon](https://github.com/frenzymath/Archon): later project-scale Lean
  baseline for DAG planning, protected declarations, and specialist subagents.
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

## Decision Rule

- No failed-compile opportunities: pilot is inconclusive.
- Eligible failures but no evidence-backed rerouting: advance to A3.
- Rerouting occurs but never makes progress: improve prompt/tool evidence before
  adding an agent.
- At least one productive recovery: scale A2 to 10 trials per task.
- Claim architecture improvement only after a matched 10 x 10 comparison,
  single-agent control, paired bootstrap, and effect-size reporting.

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
