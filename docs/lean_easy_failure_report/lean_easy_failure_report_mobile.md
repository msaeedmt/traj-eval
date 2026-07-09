# Lean Easy Failure Analysis

Mobile Markdown export generated from `data/analysis/lean_easy_failure_patterns.csv`.

## Summary

- Trials: 100
- Tasks: 10
- Solved: 0
- Trace verified: 56
- Silent failure: 0
- Validation unknown: 6
- Unsolved: 27
- Critic false accept: 59

## Proposal Alignment

- O1 localization: partially supported by trace graph construction, role attribution, and first failure stage.
- O2 taxonomy: supported by deterministic labels over reasoner, engineer, critic, and global behavior.
- O3 early prediction: not claimed for this 100-trace slice.

## Per-Task Pattern Table

| Task | Trials | Solved | Silent failure | Unknown | Unsolved | Dominant engineer label | Dominant global pattern |
|---|---:|---:|---:|---:|---:|---|---|
| easy_fatem_011 | 10 | 0 | 0 | 0 | 0 | no_submission | critic_masking |
| easy_fatem_012 | 10 | 0 | 0 | 0 | 0 | application_type_mismatch | critic_masking |
| easy_fatem_019 | 10 | 0 | 0 | 1 | 4 | no_submission | tool_overuse |
| easy_fatem_020 | 10 | 0 | 0 | 0 | 5 | no_submission | tool_overuse |
| easy_fatem_041 | 10 | 0 | 0 | 0 | 0 | no_submission | critic_masking |
| easy_fatem_109 | 10 | 0 | 0 | 0 | 2 | no_submission | critic_masking |
| easy_fatem_111 | 10 | 0 | 0 | 1 | 8 | no_submission | tool_overuse |
| easy_fatem_115 | 10 | 0 | 0 | 1 | 5 | no_submission | tool_overuse |
| easy_leancat_001 | 10 | 0 | 0 | 3 | 2 | compile_loop | critic_masking |
| easy_leancat_002 | 10 | 0 | 0 | 0 | 1 | no_submission | critic_masking |

## Validator Outcomes

- trace_verified: 56
- unsolved: 27
- import_error: 11
- validation_unknown: 6

## Role-Level Labels

### Engineer failure labels

- no_submission: 73
- application_type_mismatch: 11
- compile_loop: 10
- import_failure: 5
- typeclass_failure: 1

### Critic labels

- critic_false_accept: 59
- critic_missing: 41

### Global graph patterns

- critic_masking: 59
- tool_overuse: 34
- free_routing_failure: 6
- perseveration: 1

## Case Studies

### easy_fatem_111

- Math question: Let R be a ring. If a squared is zero in R, then a times x plus x times a commutes with a.
- Naive human strategy: Convert Commute to a multiplication equality, expand both sides, and rewrite a^2 to zero.
- Domain-specific LLM strategy: Use commute_iff_eq, mul_add/add_mul, mul_assoc, and simp/ring normalization with h.
- Dominant engineer label: no_submission
- Dominant critic label: critic_missing
- Dominant global pattern: tool_overuse

### easy_fatem_115

- Math question: Let R be a relation on a set A, and let the inverse relation contain the pairs whose reversed pairs belong to R. Then R is transitive if and only if its inverse relation is transitive.
- Naive human strategy: Unpack transitivity for the inverse relation and apply the original transitivity in reversed order.
- Domain-specific LLM strategy: Use Transitive/IsTrans definitions directly; avoid searching for a nonexistent special inverse lemma.
- Dominant engineer label: no_submission
- Dominant critic label: critic_missing
- Dominant global pattern: tool_overuse

### easy_leancat_001

- Math question: Let C be a category, and let the identity functor on C be given. The monoid of natural transformations from the identity functor to itself is commutative.
- Naive human strategy: Show two natural transformations are equal by extensionality and componentwise naturality.
- Domain-specific LLM strategy: Use NatTrans.ext and naturality; keep category variables and universe context intact.
- Dominant engineer label: compile_loop
- Dominant critic label: critic_false_accept
- Dominant global pattern: critic_masking

### easy_leancat_002

- Math question: Let C be a category, and let f and g be morphisms in C. If the composite f after g is monic, then g is monic.
- Naive human strategy: To prove a composed morphism is monic, cancel through the known monic factors.
- Domain-specific LLM strategy: Use the Mono definition and cancellation lemmas for composition.
- Dominant engineer label: no_submission
- Dominant critic label: critic_false_accept
- Dominant global pattern: critic_masking

## Reproducibility

- Raw traces: `data/batch/*.jsonl`
- Canonical CSV: `data/analysis/lean_easy_failure_patterns.csv`
- HTML export: `docs/lean_easy_failure_report/lean_easy_failure_report_standalone.html`
- Markdown export: `docs/lean_easy_failure_report/lean_easy_failure_report_mobile.md`
- Generate both mobile exports: `npm.cmd run build:mobile` from `docs/lean_easy_failure_report`

## Compact Trial Appendix

| Trial | Outcome | First failure | Reasoner | Engineer | Critic | Tools | Failed compiles | Takeaway |
|---|---|---|---|---|---|---:|---:|---|
| easy_fatem_011_t0 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 2 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_011_t1 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 3 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_011_t2 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 2 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_011_t3 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 3 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_011_t4 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 2 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_011_t5 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 2 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_011_t6 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 2 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_011_t7 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 2 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_011_t8 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 2 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_011_t9 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 2 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_012_t0 | trace_verified | engineer | partially_valid_strategy | application_type_mismatch | critic_false_accept | 7 | 3 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_012_t1 | trace_verified | engineer | valid_strategy | application_type_mismatch | critic_false_accept | 8 | 2 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_012_t2 | trace_verified | engineer | partially_valid_strategy | typeclass_failure | critic_false_accept | 5 | 2 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_012_t3 | trace_verified | engineer | valid_strategy | application_type_mismatch | critic_false_accept | 8 | 3 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_012_t4 | trace_verified | engineer | partially_valid_strategy | compile_loop | critic_false_accept | 6 | 2 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_012_t5 | trace_verified | engineer | partially_valid_strategy | application_type_mismatch | critic_false_accept | 11 | 5 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_012_t6 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 4 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_012_t7 | trace_verified | engineer | valid_strategy | application_type_mismatch | critic_false_accept | 5 | 1 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_012_t8 | trace_verified | engineer | partially_valid_strategy | compile_loop | critic_false_accept | 5 | 1 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_012_t9 | trace_verified | engineer | partially_valid_strategy | application_type_mismatch | critic_false_accept | 3 | 1 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_019_t0 | unsolved | engineer | valid_strategy | no_submission | critic_missing | 14 | 1 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_fatem_019_t1 | import_error | engineer | valid_strategy | no_submission | critic_missing | 14 | 2 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_fatem_019_t2 | validation_unknown | engineer | valid_strategy | application_type_mismatch | critic_missing | 14 | 3 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_fatem_019_t3 | import_error | engineer | valid_strategy | no_submission | critic_missing | 14 | 2 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_fatem_019_t4 | import_error | engineer | valid_strategy | no_submission | critic_missing | 14 | 2 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_fatem_019_t5 | unsolved | reasoner | no_real_strategy | no_submission | critic_missing | 12 | 0 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_fatem_019_t6 | unsolved | engineer | valid_strategy | no_submission | critic_missing | 14 | 1 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_fatem_019_t7 | unsolved | reasoner | no_real_strategy | no_submission | critic_missing | 7 | 0 | O2 evidence: engineer label no_submission localizes a concrete Lean failure mode; O3 is not claimed. Proposal groundi... |
| easy_fatem_019_t8 | import_error | engineer | valid_strategy | import_failure | critic_missing | 14 | 2 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_fatem_019_t9 | import_error | engineer | valid_strategy | no_submission | critic_missing | 14 | 1 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_fatem_020_t0 | import_error | engineer | valid_strategy | import_failure | critic_false_accept | 6 | 2 | O1/O2 evidence: critic approval masked a validator-visible proof failure; O3 is not claimed. Proposal grounding: READ... |
| easy_fatem_020_t1 | import_error | engineer | valid_strategy | import_failure | critic_false_accept | 6 | 2 | O1/O2 evidence: critic approval masked a validator-visible proof failure; O3 is not claimed. Proposal grounding: READ... |
| easy_fatem_020_t2 | unsolved | engineer | valid_strategy | no_submission | critic_missing | 8 | 6 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_fatem_020_t3 | unsolved | reasoner | no_real_strategy | no_submission | critic_missing | 5 | 0 | O2 evidence: engineer label no_submission localizes a concrete Lean failure mode; O3 is not claimed. Proposal groundi... |
| easy_fatem_020_t4 | import_error | engineer | valid_strategy | no_submission | critic_missing | 14 | 6 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_fatem_020_t5 | unsolved | engineer | valid_strategy | no_submission | critic_missing | 7 | 6 | O2 evidence: engineer label no_submission localizes a concrete Lean failure mode; O3 is not claimed. Proposal groundi... |
| easy_fatem_020_t6 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 2 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_020_t7 | unsolved | engineer | valid_strategy | no_submission | critic_missing | 8 | 6 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_fatem_020_t8 | import_error | engineer | valid_strategy | import_failure | critic_missing | 14 | 7 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_fatem_020_t9 | unsolved | engineer | valid_strategy | no_submission | critic_missing | 8 | 6 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_fatem_041_t0 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 2 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_041_t1 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 2 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_041_t2 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 2 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_041_t3 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 3 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_041_t4 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 2 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_041_t5 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 2 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_041_t6 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 2 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_041_t7 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 2 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_041_t8 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 2 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_041_t9 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 3 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_109_t0 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 3 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_109_t1 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 4 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_109_t2 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 3 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_109_t3 | unsolved | reasoner | no_real_strategy | no_submission | critic_missing | 12 | 0 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_fatem_109_t4 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 3 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_109_t5 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 3 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_109_t6 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 4 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_109_t7 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 4 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_109_t8 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 9 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_109_t9 | unsolved | reasoner | no_real_strategy | no_submission | critic_missing | 2 | 0 | O2 evidence: engineer label no_submission localizes a concrete Lean failure mode; O3 is not claimed. Proposal groundi... |
| easy_fatem_111_t0 | validation_unknown | engineer | valid_strategy | compile_loop | critic_missing | 14 | 8 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_fatem_111_t1 | unsolved | engineer | valid_strategy | no_submission | critic_missing | 9 | 6 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_fatem_111_t2 | import_error | engineer | valid_strategy | no_submission | critic_missing | 10 | 6 | O2 evidence: global behavior label perseveration explains failure beyond final accuracy; O3 is not claimed. Proposal... |
| easy_fatem_111_t3 | unsolved | engineer | valid_strategy | no_submission | critic_missing | 10 | 6 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_fatem_111_t4 | unsolved | engineer | valid_strategy | no_submission | critic_missing | 9 | 6 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_fatem_111_t5 | unsolved | engineer | valid_strategy | no_submission | critic_missing | 11 | 6 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_fatem_111_t6 | unsolved | engineer | valid_strategy | no_submission | critic_missing | 9 | 6 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_fatem_111_t7 | unsolved | engineer | valid_strategy | no_submission | critic_missing | 10 | 6 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_fatem_111_t8 | unsolved | engineer | valid_strategy | no_submission | critic_missing | 9 | 6 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_fatem_111_t9 | unsolved | engineer | valid_strategy | no_submission | critic_missing | 11 | 6 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_fatem_115_t0 | unsolved | engineer | valid_strategy | no_submission | critic_missing | 12 | 6 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_fatem_115_t1 | unsolved | engineer | valid_strategy | no_submission | critic_missing | 10 | 6 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_fatem_115_t2 | trace_verified | engineer | valid_strategy | application_type_mismatch | critic_false_accept | 11 | 5 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_115_t3 | validation_unknown | engineer | valid_strategy | application_type_mismatch | critic_missing | 14 | 3 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_fatem_115_t4 | trace_verified | engineer | valid_strategy | no_submission | critic_false_accept | 5 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_115_t5 | trace_verified | engineer | valid_strategy | application_type_mismatch | critic_false_accept | 10 | 4 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_115_t6 | unsolved | engineer | valid_strategy | no_submission | critic_missing | 10 | 6 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_fatem_115_t7 | unsolved | engineer | valid_strategy | no_submission | critic_missing | 4 | 1 | O2 evidence: engineer label no_submission localizes a concrete Lean failure mode; O3 is not claimed. Proposal groundi... |
| easy_fatem_115_t8 | trace_verified | engineer | valid_strategy | application_type_mismatch | critic_false_accept | 10 | 5 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_fatem_115_t9 | unsolved | engineer | valid_strategy | no_submission | critic_missing | 10 | 6 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_leancat_001_t0 | validation_unknown | engineer | valid_strategy | compile_loop | critic_missing | 14 | 7 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_leancat_001_t1 | validation_unknown | engineer | valid_strategy | compile_loop | critic_missing | 14 | 7 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_leancat_001_t2 | trace_verified | engineer | partially_valid_strategy | no_submission | critic_false_accept | 2 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_leancat_001_t3 | unsolved | engineer | valid_strategy | no_submission | critic_missing | 13 | 6 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_leancat_001_t4 | trace_verified | engineer | partially_valid_strategy | no_submission | critic_false_accept | 5 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_leancat_001_t5 | unsolved | engineer | valid_strategy | no_submission | critic_missing | 11 | 6 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_leancat_001_t6 | validation_unknown | engineer | valid_strategy | compile_loop | critic_missing | 14 | 3 | O2 evidence: global behavior label tool_overuse explains failure beyond final accuracy; O3 is not claimed. Proposal g... |
| easy_leancat_001_t7 | trace_verified | engineer | partially_valid_strategy | compile_loop | critic_false_accept | 8 | 1 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_leancat_001_t8 | trace_verified | engineer | partially_valid_strategy | no_submission | critic_false_accept | 4 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_leancat_001_t9 | trace_verified | engineer | valid_strategy | compile_loop | critic_false_accept | 10 | 5 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_leancat_002_t0 | trace_verified | engineer | partially_valid_strategy | no_submission | critic_false_accept | 5 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_leancat_002_t1 | unsolved | reasoner | no_real_strategy | no_submission | critic_missing | 6 | 0 | O2 evidence: engineer label no_submission localizes a concrete Lean failure mode; O3 is not claimed. Proposal groundi... |
| easy_leancat_002_t2 | trace_verified | engineer | partially_valid_strategy | no_submission | critic_false_accept | 5 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_leancat_002_t3 | trace_verified | engineer | partially_valid_strategy | no_submission | critic_false_accept | 4 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_leancat_002_t4 | import_error | engineer | partially_valid_strategy | import_failure | critic_false_accept | 4 | 2 | O1/O2 evidence: critic approval masked a validator-visible proof failure; O3 is not claimed. Proposal grounding: READ... |
| easy_leancat_002_t5 | trace_verified | engineer | partially_valid_strategy | no_submission | critic_false_accept | 4 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_leancat_002_t6 | trace_verified | engineer | partially_valid_strategy | no_submission | critic_false_accept | 4 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_leancat_002_t7 | trace_verified | engineer | partially_valid_strategy | compile_loop | critic_false_accept | 5 | 1 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_leancat_002_t8 | trace_verified | engineer | partially_valid_strategy | no_submission | critic_false_accept | 5 | 0 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |
| easy_leancat_002_t9 | trace_verified | engineer | partially_valid_strategy | compile_loop | critic_false_accept | 6 | 1 | O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed. Proposal groun... |

## Lean Trajectory Appendix

### easy_fatem_111_t0

- Task: easy_fatem_111
- Declared success: false
- Submitted equals last verified: true
- Failed compiles: 8

Formal statement:

```lean
theorem fatem_111_commute_of_pow_two_zero (R : Type) [Ring R] (a : R) (h : a ^ 2 = 0) :
    ∀ x : R, Commute (a * x + x * a) a
```

Submitted code:

```lean
import Mathlib

theorem test (R : Type) [Ring R] (a : R) (h : a ^ 2 = 0) :
    a * a = 0 := by
  simpa [pow_two] using h
```

Last verified code:

```lean
import Mathlib

theorem test (R : Type) [Ring R] (a : R) (h : a ^ 2 = 0) :
    a * a = 0 := by
  simpa [pow_two] using h
```

check_lean calls:

- seq 1: compiled=unknown, sorry_free=unknown
- seq 3: compiled=unknown, sorry_free=unknown
- seq 5: compiled=unknown, sorry_free=unknown
- seq 7: compiled=unknown, sorry_free=unknown
- seq 9: compiled=unknown, sorry_free=unknown
- seq 12: compiled=false, sorry_free=true
- seq 14: compiled=false, sorry_free=true
- seq 16: compiled=false, sorry_free=true
- seq 18: compiled=false, sorry_free=true
- seq 20: compiled=false, sorry_free=true
- seq 22: compiled=true, sorry_free=true
- seq 24: compiled=false, sorry_free=true
- seq 26: compiled=false, sorry_free=true
- seq 28: compiled=false, sorry_free=true

Compact role timeline:

- #0 system / message: Prove this Lean 4 theorem (source: FATE-M, difficulty: easy). Informal statement: Let R be a ring. If a squared is zero in R, then a times x plus x times a commutes with a. Form...
- #1 reasoner / tool_call / search_lemmas: {"query":"Commute definition and properties"}
- #2 executor / execution_result: Top matches (name signature -- description): Commute [Mul S] (a b : S) : Prop -- Commuting elements Function.Commute (f g : α → α) : Prop -- Commuting functions Commute.eq {a b...
- #3 reasoner / tool_call / search_lemmas: {"query":"add_commute_left or add_commute_right"}
- #4 executor / execution_result: Top matches (name signature -- description): AddCommute {S : Type u_3} → [Add S] → S → S → Prop -- Additive commutativity of two elements add_left_comm ∀ {G : Type u_3} [inst :...
- #5 reasoner / tool_call / search_lemmas: {"query":"Commute.add_left or Commute.add_right"}
- #6 executor / execution_result: Top matches (name signature -- description): Commute.add_left [Distrib R] {a b c : R} : Commute a c → Commute b c → Commute (a + b) c -- Addition Preserves Commutativity in Dist...
- #7 reasoner / tool_call / search_lemmas: {"query":"Commute.mul_left or Commute.mul_right"}
- #8 executor / execution_result: Top matches (name signature -- description): commute_lmul_rmul (a : A) : Commute (L a) (R a) -- Commutation of Left and Right Multiplication Operators LinearMap.commute_mulLeft_...
- #9 reasoner / tool_call / search_lemmas: {"query":"Commute.mul_left"}
- #10 executor / execution_result: Top matches (name signature -- description): mul_left_comm (a b c : G) : a * (b * c) = b * (a * c) -- Left-Commutativity of Multiplication in a Commutative Semigroup Commute.mul...
- #11 reasoner / message / to engineer: Strategy: 1. **Goal**: Prove that for any $x \in R$, the element $a * x + x * a$ commutes with $a$, given $a^2 = 0$. 2. **Definition of Commute**: Recall that `Commute u v` is e...
- #12 engineer / tool_call / check_lean: import Mathlib theorem fatem_111_commute_of_pow_two_zero (R : Type) [Ring R] (a : R) (h : a ^ 2 = 0) : ∀ x : R, Commute (a * x + x * a) a := by intro x rw [commute_iff_eq] calc...
- #13 executor / execution_result: {'compiled': False, 'sorry_free': True, 'n_sorries': 0, 'n_errors': 1, 'errors': [{'severity': 'error', 'data': '', 'line': None, 'column': None}], 'sorries': [], 'warnings': []...
- #14 engineer / tool_call / check_lean: import Mathlib theorem fatem_111_commute_of_pow_two_zero (R : Type) [Ring R] (a : R) (h : a ^ 2 = 0) : ∀ x : R, Commute (a * x + x * a) a := by intro x rw [commute_iff_eq] calc...
- #15 executor / execution_result: {'compiled': False, 'sorry_free': True, 'n_sorries': 0, 'n_errors': 1, 'errors': [{'severity': 'error', 'data': '', 'line': None, 'column': None}], 'sorries': [], 'warnings': []...
- #16 engineer / tool_call / check_lean: import Mathlib theorem fatem_111_commute_of_pow_two_zero (R : Type) [Ring R] (a : R) (h : a ^ 2 = 0) : ∀ x : R, Commute (a * x + x * a) a := by intro x rw [commute_iff_eq] simp...
- #17 executor / execution_result: {'compiled': False, 'sorry_free': True, 'n_sorries': 0, 'n_errors': 1, 'errors': [{'severity': 'error', 'data': '.traj_eval_tmp\\check_ec9e9441297e421084dcf2a17c1afee3.lean:8:6:...
- #18 engineer / tool_call / check_lean: import Mathlib theorem fatem_111_commute_of_pow_two_zero (R : Type) [Ring R] (a : R) (h : a ^ 2 = 0) : ∀ x : R, Commute (a * x + x * a) a := by intro x rw [commute_iff_eq] have...
- #19 executor / execution_result: {'compiled': False, 'sorry_free': True, 'n_sorries': 0, 'n_errors': 1, 'errors': [{'severity': 'error', 'data': '', 'line': None, 'column': None}], 'sorries': [], 'warnings': []...
- #20 engineer / tool_call / check_lean: import Mathlib theorem fatem_111_commute_of_pow_two_zero (R : Type) [Ring R] (a : R) (h : a ^ 2 = 0) : ∀ x : R, Commute (a * x + x * a) a := by intro x rw [commute_iff_eq] simp...
- #21 executor / execution_result: {'compiled': False, 'sorry_free': True, 'n_sorries': 0, 'n_errors': 1, 'errors': [{'severity': 'error', 'data': '', 'line': None, 'column': None}], 'sorries': [], 'warnings': []...
- #22 engineer / tool_call / check_lean: import Mathlib theorem test (R : Type) [Ring R] (a : R) (h : a ^ 2 = 0) : a * a = 0 := by simpa [pow_two] using h
- #23 executor / execution_result: {'compiled': True, 'sorry_free': True, 'n_sorries': 0, 'n_errors': 0, 'errors': [], 'sorries': [], 'warnings': [], 'summary': 'compiled: true; sorries: 0; errors: 0'}
- #24 engineer / tool_call / check_lean: import Mathlib theorem fatem_111_commute_of_pow_two_zero (R : Type) [Ring R] (a : R) (h : a ^ 2 = 0) : ∀ x : R, Commute (a * x + x * a) a := by intro x rw [commute_iff_eq] have...
- #25 executor / execution_result: {'compiled': False, 'sorry_free': True, 'n_sorries': 0, 'n_errors': 1, 'errors': [{'severity': 'error', 'data': '', 'line': None, 'column': None}], 'sorries': [], 'warnings': []...
- #26 engineer / tool_call / check_lean: import Mathlib theorem fatem_111_commute_of_pow_two_zero (R : Type) [Ring R] (a : R) (h : a ^ 2 = 0) : ∀ x : R, Commute (a * x + x * a) a := by intro x rw [commute_iff_eq] have...
- #27 executor / execution_result: {'compiled': False, 'sorry_free': True, 'n_sorries': 0, 'n_errors': 1, 'errors': [{'severity': 'error', 'data': '', 'line': None, 'column': None}], 'sorries': [], 'warnings': []...
- #28 engineer / tool_call / check_lean: import Mathlib theorem fatem_111_commute_of_pow_two_zero (R : Type) [Ring R] (a : R) (h : a ^ 2 = 0) : ∀ x : R, Commute (a * x + x * a) a := by intro x rw [commute_iff_eq] have...
- #29 executor / execution_result: {'compiled': False, 'sorry_free': True, 'n_sorries': 0, 'n_errors': 1, 'errors': [{'severity': 'error', 'data': '', 'line': None, 'column': None}], 'sorries': [], 'warnings': []...

