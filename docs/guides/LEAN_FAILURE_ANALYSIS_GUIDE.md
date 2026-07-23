# Lean Trajectory Failure Analysis Guide

This guide defines the evidence contract for diagnosing the 100 existing Lean
agent traces in **data/batch/**. It is an analysis of immutable runs, not a
claim that every possible agent failure has been enumerated.

No published taxonomy is exhaustive. The report therefore uses a layered,
multi-label model: an observed compiler symptom, its supported causal
interpretation, the verification layer that detected it, and its effect on the
rest of the trajectory are stored separately.

## Scientific status

This dataset is the fully step-verifiable Lean comparison in the trajectory
proposal, but only the kernel can supply final proof truth.

- **O1 — localisation: partial evidence.** Event IDs and causal edges exist, but
  all raw event anchors are null. The report may localise reviewed incidents to
  an event; it cannot report validated first-anchor precision/recall.
- **O2 — classification: exploratory evidence.** All 100 traces have
  agent-reviewed labels, but there is no independent expert gold set. Do not
  claim the proposal's precision/recall target of 0.8.
- **O3 — comparison/early warning: not tested.** These traces use one
  architecture, backbone, grounding setting, and stress level.
- **Warehouse evidence used:** the private warehouse has no matched Lean control
  for this slice. STARGAZER rankings are excluded from Lean counts.

The reviewed trace-only partition is 55 approved exact-target candidates, four
approved statement drifts, one exact target without critic approval, and 40
incomplete workflows. Across 341 check_lean attempts, 123 were accepted, 132
were real Lean rejections, and 86 returned an opaque infrastructure-unknown
result. These are process facts, not final kernel revalidation results.

## Literature clarification

The operational labels combine complementary sources:

- [FATE](https://arxiv.org/abs/2511.02872): natural-language gaps,
  hallucination/no progression/reasoning problems, Mathlib hallucination, Lean
  proficiency, general-capability failures, and informal-to-formal
  misalignment.
- [LeanCat](https://arxiv.org/abs/2512.24796): mathematical failures,
  grammar/elaboration errors, library hallucination, missing bridges, and
  specification alteration.
- [MAST](https://arxiv.org/abs/2503.13657): system-design, inter-agent
  misalignment, stopping, repetition, information sharing, and incomplete or
  incorrect verification failures.
- [Faults in Our Formal Benchmarking](https://arxiv.org/abs/2606.29493):
  specification/fidelity defects, evaluation loopholes, and version drift. A
  kernel proves the supplied formal proposition; it does not prove that a
  benchmark faithfully expresses an informal problem.
- [AgentRx](https://arxiv.org/abs/2602.02475): retain every incident, but define
  the critical failure as the first event after which the unsuccessful
  trajectory never recovers.

These sources clarify the search space; they do not license a universal
"all agent errors" claim.

## Evidence layers

Keep these layers independent:

1. **Raw trace fact:** message, tool call, tool result, compiler diagnostic,
   handoff, or critic decision.
2. **Observed symptom:** what is directly visible, such as
   application_type_mismatch or opaque_compiler_failure.
3. **Causal label:** a bounded interpretation supported by the evidence, such
   as lean_type_failure or missing_critic_review.
4. **Recovery:** whether a later sorry-free target check repaired the incident.
5. **Critical failure:** the first unrecovered incident, or null for a
   successful/recovered trajectory.
6. **Verification:** trace-only, kernel accepted/rejected, or infrastructure
   unknown.
7. **Downstream effect:** missing target, changed statement, incomplete review,
   or critic masking.

A successful trial can contain recovered failures. An unsuccessful trial can
contain successful helper/probe checks. Neither fact is contradictory.

## Operational taxonomy

### Benchmark and harness

Use only with benchmark-level evidence:

- specification defect
- informal/formal fidelity mismatch
- evaluation loophole
- dependency or version drift

An unknown constant written by an agent is not an import/environment failure.
invalid_import_path is an agent API/library error unless the required module is
demonstrably missing from the pinned environment.

### Retrieval and reasoning

- no_actionable_plan
- mathematical gap or false reasoning
- query drift or perseveration
- API/library hallucination
- reasoning/action mismatch

Do not infer a mathematical error from a compiler message alone. When the trace
only shows an opaque failed tool response, use tooling_diagnostic_unknown with
confidence not_observable.

### Lean formalisation symptoms

- unknown_symbol
- parser_or_syntax_error
- application_type_mismatch
- type_mismatch
- typeclass_resolution
- invalid_field_projection
- tactic_failure
- unsolved_goals
- invalid_import_path
- opaque_compiler_failure
- other_lean_diagnostic
- sorry_pseudo_pass
- statement_drift
- regression_after_success

The corresponding causal labels are deliberately broader:
lean_elaboration_failure, lean_type_failure, lean_tactic_failure,
api_or_library_hallucination, helper_substitution, and statement_drift.

### Coordination and stopping

- premature_termination
- missing_critic_review
- perseveration
- missing handoff or context loss
- incomplete workflow

The current runner does not log an explicit event-budget termination reason.
Therefore premature_termination is tentative when inferred only from the trace
ending.

### Critic and verification

- incomplete_verification
- incorrect_verification
- missed_statement_drift
- critic_masking

critic_false_accept applies when the workflow approves an artifact that either
contradicts the critic's own relevant failed recheck or is independently
rejected by the strict kernel gate. The narrower critic_masking label requires
the trace-internal contradiction; therefore all four approved statement drifts
are false accepts, but only the approval after a failed recheck is critic
masking. Kernel-off trace_verified is never, by itself, a false accept.

## Exact target contract

For this analysis, the dataset theorem type is the contract.

- Ignore comments and whitespace when comparing the declaration, but preserve
  the supplied theorem name as part of the header contract.
- Preserve parameters, typeclass assumptions, and proposition exactly.
- A compiled helper theorem, example, or #check is not the target.
- Transitive to IsTrans is statement drift even if mathematically equivalent.
- sorry and admit are prohibited placeholders, not proof success.
- A candidate is submitted only when the workflow explicitly accepts the
  verified target. A previous successful probe cannot be silently promoted to a
  submission.

Kernel validation must independently check:

1. candidate compilation;
2. absence of sorry/admit;
3. the proof body under the original dataset statement;
4. absence of non-standard axioms.

The canonical analyzer defaults to **--kernel required** and writes no report
when the pinned Lean environment is unavailable. **--kernel auto** and
**--kernel off** are explicit provisional modes.

## Review record

**data/analysis/lean_easy_failure_reviews.jsonl** contains exactly one
hash-bound record per trial:

~~~
trial_id, task_id, source_file, source_sha256
review_status, review_confidence
candidate { kind, event_seq, statement_match, workflow_approved,
            submission_accepted, kernel_status }
workflow { outcome, approval_event_seq, critic_check_count }
symptom_codes[], causal_labels[], incidents[]
critical_failure | null
recovered_failure_seqs[], downstream_effects[]
assessments, trace_evidence, task_diagnosis
~~~

Each incident includes an evidence event, role, symptom, supported causal
labels, recovery status, confidence, and a short evidence excerpt. Allowed
confidence values are:

- confirmed: directly visible statement/decision/diagnostic;
- strong: well-supported interpretation with no known contradiction;
- tentative: plausible but the trace omits a decisive event;
- not_observable: the tool result has no usable diagnostic.

The analyzer refuses a review when the raw SHA-256, event references, taxonomy
codes, candidate classification, or workflow classification no longer match the
trace.

## Per-task reading sequence

For every trial:

1. Read the supplied theorem and write the plain mathematical proof strategy.
2. State the Lean-specific strategy and likely API traps.
3. Pair each check_lean call with its result; count search_lemmas separately.
4. Classify every failed result without discarding recovered errors.
5. Distinguish exact target, changed statement, helper/probe, and no candidate.
6. Inspect reasoner-to-engineer handoff and whether revisions use compiler
   evidence.
7. Inspect critic rechecks and the final accepted candidate.
8. Select the first unrecovered incident, not the first error in the file.
9. Apply independent kernel validation before making correctness claims.

The graph view is an event timeline with declared causal edges. In this slice,
97 traces are connected linear chains and three are two-component timelines.
There is no branching or merging evidence that would justify a stronger graph-
causal claim.

## Acceptance criteria

The 100-trial analysis is ready only when:

- raw JSONL SHA-256 hashes are unchanged;
- review and trace IDs match exactly;
- all event references and taxonomy codes validate;
- exact-target, statement-drift, helper/probe, and missing candidates are
  separate;
- recovered incidents never become terminal labels;
- every unsuccessful workflow has a critical incident or an explicit
  not_observable explanation;
- CSV and report JSON share one snapshot hash and the same 100 trial IDs;
- kernel-unavailable reports say provisional and make no O1/O2 detector-quality
  or O3 comparison claim.
