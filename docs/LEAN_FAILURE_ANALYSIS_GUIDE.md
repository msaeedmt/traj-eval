# Lean Failure Analysis Guide

This guide defines how to analyze the existing Lean-agent JSONL traces. It is
an analysis guide, not a new runtime design.

Keep the workflow small:

```text
math question -> global causal trace -> reasoner strategy -> engineer code path -> critic review -> validator result
```

Do not add a dashboard, database, new trace schema, graph visualization, or new
runtime before this analysis is useful on the current easy traces.

## 1. Per-Question Math Analysis

Start with the theorem itself before reading the agent trace. This prevents
mixing up theorem difficulty, Lean API friction, and agent behavior.

For each task, write:

```text
math_question
naive_human_strategy
domain_specific_LLM_strategy
key_Lean_objects_or_lemmas
expected_difficulty_for_human
expected_difficulty_for_LLM_Lean_agent
```

The naive human strategy should be written for mathematical understanding, not
for showing off automation. Prefer plain proof structure.

Also write a domain-specific LLM strategy. This is the scalable reference:
instead of hand-designing every proof as a human, define the operational proof
plan a strong Lean-specialized model should infer from the theorem domain. The
human strategy explains the math; the domain-specific LLM strategy explains how
that math should become a Lean action plan.

The domain-specific LLM strategy should include:

```text
domain_family
target_shape
canonical_unfolds
likely_lemmas_or_APIs
proof_skeleton
known_API_traps
validation_checklist
```

Example:

```text
FATEM111
Question: if a^2 = 0, prove a*x + x*a commutes with a.
Naive strategy: unfold Commute, expand both sides, use associativity,
distributivity, and a*a = 0.
Domain-specific LLM strategy: classify as noncommutative ring plus Commute.
Unfold Commute, rewrite a^2 = 0 to a*a = 0, expand with add_mul, mul_add,
mul_assoc, and pow_two, and avoid proving only a helper theorem.
Risk: noncommutative ring manipulation plus the Commute API.
```

Example:

```text
FATEM115
Question: prove transitivity is preserved by reversing a relation.
Naive strategy: unfold Transitive. In each direction, reverse the order of the
two relation hypotheses.
Domain-specific LLM strategy: classify as relation/transitivity. Unfold
Transitive, solve each direction by swapping hypothesis order, preserve the
exact target statement, and watch Transitive versus IsTrans API confusion.
Risk: Transitive vs IsTrans API confusion.
```

## 2. Global Graph / Coordination Analysis

After the math framing, follow the JSONL causal graph and event sequence. This
is the global guide for reading the run before blaming any single role.

Use the existing trace tools:

```text
read_trial(path) -> events
build_graph(events)
causal_order(events)
extract_artifacts(events)
detect_perseveration(tool_calls)
```

Ask:

```text
How many agent turns happened?
How many tool calls happened?
Which role dominates the trace?
Where is the first meaningful divergence?
Does the agent stick to one strategy or revise it?
Are revisions productive, or just drift?
Is there a dead loop or perseveration?
Does control return to the right agent after a failure?
Does reasoner-engineer-critic communication help, or add noise?
```

Use simple global labels:

```text
productive_revision
strategy_drift
dead_loop
perseveration
critic_masking
tool_overuse
tool_underuse
reasoner_engineer_mismatch
engineer_critic_mismatch
free_routing_failure
```

The graph-level question is:

```text
What did the system do as a substrate, not only what answer did it produce?
```

## 3. Reasoner Strategy Analysis

Inspect reasoner messages and search/tool calls.

Ask:

```text
Did the reasoner identify the theorem shape?
Did it propose a mathematically valid proof strategy?
Did it choose the right Lean objects or API?
Did it use search_lemmas appropriately?
Did it revise after compiler evidence?
Did revision improve the proof, or drift to a different theorem/API?
```

Use simple reasoner labels:

```text
valid_strategy
partially_valid_strategy
wrong_api_strategy
wrong_statement_strategy
strategy_drift
no_real_strategy
```

Compare the reasoner strategy against the naive human strategy. A strategy can
be mathematically valid but still too vague for Lean. Record that distinction.

## 4. Engineer Failure Analysis

Inspect engineer tool calls, submitted proof, compile results, and handoffs.

Ask:

```text
Did the engineer implement the reasoner strategy?
Did the engineer call check_lean before handoff?
Did the engineer prove the original statement or a changed statement?
Was the failure an import, API, application, typeclass, or type mismatch?
Did the engineer hallucinate a lemma, class, theorem, or notation?
Did the engineer ask the reasoner for more guidance?
Did the engineer ask the critic for confidence even when compiling failed?
Did the engineer repeatedly submit similar failing code?
```

Use simple engineer labels:

```text
import_failure
application_type_mismatch
typeclass_failure
hallucinated_lemma
wrong_statement
api_confusion
no_submission
compile_loop
verified_then_changed
```

The engineer-level question is:

```text
Did the code path faithfully implement the intended strategy and original theorem?
```

## 5. Critic Review Analysis

Inspect critic messages, decisions, and tool calls.

Ask:

```text
Did the critic call check_lean?
Did the critic approve without compiling?
Did the critic check statement match, not only compile success?
Did the critic approve a false proof?
Did the critic send the task back to the engineer?
Did the critic notice wrong API or changed theorem?
Did the critic's confidence match validator evidence?
```

Use simple critic labels:

```text
critic_compile_checked
critic_no_compile_check
critic_statement_checked
critic_shallow_approval
critic_false_accept
critic_sent_back
critic_missing
```

The critic-level question is:

```text
Was the critic an independent verifier, or only a conversational approver?
```

## Minimal Evidence Table

The first implementation should produce one human-readable row per trial:

```text
task_id
trial_id
math_question
naive_human_strategy
domain_specific_LLM_strategy
global_graph_pattern
reasoner_strategy_summary
reasoner_strategy_label
engineer_behavior_summary
engineer_failure_label
critic_behavior_summary
critic_label
validator_outcome
first_failure_stage
math_diagnosis
dataset_label_diagnosis
```

This table is not a new trace schema. It is a report artifact derived from the
existing JSONL traces.

## YAGNI Boundary

Do not build:

```text
dashboard
database
new trace schema
new runtime
graph visualization first
general multi-benchmark framework
```

Use the current data first:

```text
data/batch/*_t*.jsonl
```

The first implementation after this guide should only create:

```text
data/analysis/lean_easy_failure_patterns.csv
docs/LEAN_EASY_FAILURE_PATTERN_ANALYSIS.md
```

## Acceptance Criteria

One trial is well analyzed only when the report answers:

```text
What was the math question?
What was the expected human strategy?
What does the causal graph show globally?
What did the reasoner try?
Did the engineer follow it?
What failed in Lean coding?
Did the critic review correctly?
What did the validator say?
```

Advisor-facing conclusions should be supported by trace evidence, for example:

```text
FATEM111 is valid but agent-hard because the expected strategy requires
noncommutative algebra and Commute expansion.

FATEM115 is valid and human-easy, but failures come from Transitive/IsTrans API
confusion and critic statement-match weakness.

Some failures are coordination or review failures visible only in the trajectory
graph, not theorem difficulty.
```
