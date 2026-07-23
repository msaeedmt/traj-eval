# Lean Agent Behavior Analysis

## Reading Status

This report is a low-level reading of 124 Lean-agent JSONL trajectories. It is
not a new benchmark run and it does not use an LLM to diagnose another LLM.
Every behavioral claim below is grounded in raw events, the existing reviewed
easy-trace records, compiler responses, the repository graph builder, or an
explicitly marked historical summary.

The report follows three local sources:

- the [NLP Lab proposal](../reference/NLP_Lab___Project_Proposal.pdf), which asks whether
  trajectory evidence can localize failures that output-only evaluation misses;
- the [Lean failure analysis guide](../guides/LEAN_FAILURE_ANALYSIS_GUIDE.md), which
  separates symptoms, bounded causal interpretations, recovery, critical
  failure, and independent verification;
- the educational ordering of the separate 100-trial Vibecoding Lean lab:
  understand the theorem, inspect the agent strategy, inspect tool evidence,
  judge the critic, and only then read the final verdict. That application is a
  structural reference, not a dependency or evidence source.

### Frozen Snapshot

| Item | Value |
|---|---:|
| Snapshot time | 2026-07-12 09:51:09 Europe/Berlin |
| JSONL traces | 124 |
| Canonical easy | 100 |
| Recovery prompt | 10 |
| Tool-routed easy | 3 |
| Interrupted audit | 1 |
| Medium subgoal | 10 |
| Deep forensic records | 62 |
| Compact passed records | 62 |
| Events | 3,948 |
| Pre-consolidation combined manifest SHA-256 | `c21b537e290d85949a639595fb8c290709fea4b6230b9a32725c4ab9bf7663a8` |

The frozen snapshot used for this report is retained in an external historical
archive. The combined hash is SHA-256 over its pre-consolidation sorted manifest
of relative path, tab, full-file SHA-256, and newline. It is path-sensitive and
therefore intentionally remains a historical provenance value after evidence
relocation; the per-file SHA-256 values below identify the source bytes. All ten
medium files contain an explicit terminal event; no growing medium file is
treated as complete by inference.

| Cohort | Solved label | Unsolved label | Silent-failure label | Other |
|---|---:|---:|---:|---:|
| Canonical easy, current reviewed analysis | 56 | 40 | 4 | 0 |
| Recovery, historical summary | 6 | 2 | 2 | 0 |
| Tool-routed easy, historical summary | 0 | 2 | 1 | 0 |
| Interrupted audit | 0 | 0 | 0 | 1 interrupted |
| Medium subgoals, completed batch summary | 0 | 10 | 0 | 0 |

Only the canonical row is treated as current strict reviewed outcome evidence.
The experimental labels are retained for provenance and analyzed against their
raw traces below.

### Answer First

1. **The reasoner is often mathematically adequate but operationally weak.**
   FATEM111 has the correct noncommutative expansion in all ten canonical
   strategies, yet no canonical run reaches an accepted target. FATEM019 agents
   usually know that prime moduli should yield fields, but fail at the exact
   proposition-to-typeclass and quotient API bridge.
2. **The original easy architecture is almost entirely one-way, while typed
   medium routing creates return communication without solving.** Across all
   124 traces there are 127 reasoner-to-engineer, 73 engineer-to-critic, 11
   engineer-to-reasoner, and 22 critic-to-engineer routes. The medium batch
   contributes ten of the 11 engineer-to-reasoner returns and 15 of the 22
   critic returns.
3. **Compilation is not one kind of evidence.** The ten medium runs contain 282
   resolved probes, 91 resolved subgoal checks, and 19 critic reviews. Of 204
   successful compiler results, 166 are probes, 19 are candidate artifacts,
   and 19 are reviews of those same candidates. Thirteen subgoals are accepted;
   no final theorem is completed.
4. **The critic is usually terminal, not corrective.** The canonical 100 have
   59 approvals and 30 critic recompilations, but no critic-to-engineer return.
   FATEM115 shows the dangerous case: a changed statement can compile and be
   approved even though it does not satisfy the benchmark contract.
5. **Subgoals improve localization before they improve solving, but ledger
   acceptance is not mathematical discharge.** Every medium trial accepts at
   least one preliminary artifact. The ledger marks two nodes accepted in
   `t4`, `t5`, and `t7`; mathematical inspection downgrades `t5`'s second node
   because it defines a lift but does not prove the promised universal
   property.
6. **The data supports exploratory localization and taxonomy, not detector
   validation or early prediction.** Raw anchors are absent, reviews are not an
   independent expert gold set, and there is no matched stress progression.

## 1. Research Question And Evidence Boundary

The proposal's main question is whether intermediate-step verifiability changes
multi-agent failure spectra, and whether trace signals expose failures that a
final answer hides. In this Lean slice:

- **O1, localization: partial evidence.** Event IDs, roles, compiler results,
  subgoal IDs, and declared causal edges can locate an observed failure. Raw
  event anchors are null, so this report does not claim the proposal target of
  localization precision/recall at least 0.8.
- **O2, taxonomy: exploratory evidence.** The canonical 100 have hash-bound
  reviewed incidents. The newer experiments have deterministic trace facts and
  provisional interpretations, but no independent expert-gold annotations.
- **O3, early prediction: not tested.** Repeated trials exist, but there is no
  controlled stress sequence or matched architecture/backbone comparison.

### Five Evidence Levels That Must Not Be Collapsed

| Evidence | What it establishes | What it does not establish |
|---|---|---|
| Search result | A possibly relevant API name was retrieved | The name exists in the active imports or solves the theorem |
| Successful probe | A `#check`, helper fragment, or local expression compiled | A subgoal or target theorem was proved |
| Successful subgoal | One declared artifact compiled | Dependencies, critic acceptance, or final integration |
| Critic approval | The workflow accepted an artifact | Exact-target kernel validity |
| Independent target validation | The exact submitted theorem compiles, is sorry-free, statement-preserving, and axiom-clean | General reliability outside this task/run |

An earlier local strict rescore of the then-available 17 experimental traces
produced no first verdict after more than seven minutes and was stopped. This
is recorded as **infrastructure unknown**. It is not converted into a proof
rejection. The experiment `summary.json` verdicts remain historical labels;
the report names them as such instead of pretending they were freshly
reconfirmed.

The completed medium traces contain no submitted final artifact and no
`run_complete=true` event. Their `unsolved` label means the workflow terminated
without verified completion; it is not a fresh kernel rejection of a final
proof.

## 2. How To Read A Trajectory

### Roles

The reasoning-agent team has exactly three roles:

- **Reasoner:** identifies the mathematical route, searches for library
  objects, and should revise strategy when implementation evidence invalidates
  the plan.
- **Engineer:** translates the route into Lean, distinguishes exploratory probes
  from proof candidates, and reacts to diagnostics.
- **Critic:** checks exact-statement fidelity and compiler evidence. A useful
  rejection should return concrete evidence to the engineer.

Historical `Executor` events are non-agent tool-runtime records. Historical
`Planner` or `Repairer` labels are compatibility labels, not additional current
reasoning roles.

### Failure Record

Each failure record uses the guide's evidence layers:

1. **Raw fact:** an event, tool call, compiler response, route, or decision.
2. **Observed symptom:** for example `unknown_symbol`,
   `application_type_mismatch`, or `statement_drift`.
3. **Bounded causal label:** for example `lean_type_failure` or
   `api_or_library_hallucination`. This is not a claim about model internals.
4. **Recovery:** a later exact-target success repairs the incident.
5. **Critical failure:** the first incident after which the unsuccessful run
   never recovers.
6. **Downstream effect:** missing target, changed statement, missing review, or
   critic masking.

`R` after an incident means recovered; `U` means unrecovered. An opaque compiler
response is reported as `tooling_diagnostic_unknown`, not as a mathematical
mistake.

### Tool Purpose

Explicit `purpose` fields are preferred. Older calls are interpreted
conservatively:

- `search_lemmas`: retrieval;
- `#check`, `#print`, or synthesis query: probe;
- exact theorem declaration: target candidate;
- helper theorem or definition: helper/subgoal;
- critic `check_lean` or `review_lean`: review;
- anything ambiguous: purpose not observable.

### Graph Meaning

The graph is built with `src/traj_eval/trace_core/graph.py`. Nodes are events and
edges are recorded `caused_by` links. A route that revisits a role is a **role
cycle**, not automatically a cycle or branch in the causal graph. Of 124 traces,
114 are full event chains. Three canonical and seven medium traces have
disconnected or branching recorded structure. Medium `t3`, for example, has a
longest path of 126 over 202 nodes because return routes create alternate causal
parentage. None of this demonstrates parallel reasoning.

## 3. Mathematics Before Agent Judgment

The following references define what a mathematically informed agent should
try. They are comparison baselines, not claims that the displayed Lean route
has been certified in this snapshot.

### FATEM011: Distributivity Over Subtraction

```lean
theorem fatem_011_mul_sub_and_sub_mul {R : Type*} [Ring R] (a b c : R) :
    a * (b - c) = a * b - a * c ∧ (b - c) * a = b * a - c * a
```

- **Paper proof:** left and right distributivity give the two equalities;
  combine them as a conjunction.
- **Strong Lean strategy:** `constructor`; close the branches with `mul_sub`
  and `sub_mul`.
- **Expected subgoals:** exactly the two conjuncts.
- **API traps:** argument order distinguishes `mul_sub` from `sub_mul`; adding
  commutativity would change the assumptions.

### FATEM012: Unique Ring Homomorphism From The Integers

```lean
theorem fatem_012_existUnique_ringHom_int {R : Type*} [Ring R] :
    ∃! f : ℤ →+* R, True
```

- **Paper proof:** integer casts give a unital ring homomorphism; every unital
  ring homomorphism from `ℤ` agrees on `1`, hence on all integers.
- **Strong Lean strategy:** choose `Int.castRingHom R`, prove `True`, then use
  the `Subsingleton` instance for `ℤ →+* R`.
- **Expected subgoals:** witness, trivial predicate, uniqueness.
- **API traps:** `∃!` includes uniqueness; the predicate is literally `True`;
  manually constructing a `RingHom` creates unnecessary obligations.

### FATEM019: `ZMod n` Is A Field Exactly For Prime `n`

```lean
theorem fatem_019_zmod_isField_iff_prime (n : ℕ) :
    IsField (ZMod n) ↔ Nat.Prime n
```

- **Paper proof:** for prime `n`, every nonzero residue is coprime to `n` and
  Bezout supplies an inverse. If `n` is composite, nontrivial factors give zero
  divisors, impossible in a field.
- **Strong Lean strategy:** first locate the exact Mathlib bridge; separate the
  proposition `Nat.Prime n`, the instance `Fact (Nat.Prime n)`, a `Field`
  instance, and the proposition `IsField (ZMod n)`.
- **Expected subgoals:** prime-to-field direction, field-to-prime direction,
  and proposition/typeclass conversions.
- **API traps:** `Field`, `IsField`, `IsDomain`, and `Fact` are related but not
  interchangeable. This route is a study strategy: no canonical run proves it.

### FATEM020: Ideals In A Field

```lean
theorem fatem_020_field_ideal_eq_bot_or_top {F : Type*} [Field F]
    (I : Ideal F) : I = 0 ∨ I = ⊤
```

- **Paper proof:** if `I` contains a nonzero `x`, closure under multiplication
  by `x⁻¹` puts `1` in `I`, so `I = ⊤`; otherwise every element is zero.
- **Strong Lean strategy:** prefer a field-specific ideal dichotomy. For a
  direct proof, split on a nonzero member and make the ideal-membership steps
  explicit.
- **Expected subgoals:** zero-ideal branch and whole-ideal branch.
- **API traps:** the historical agents repeatedly misuse
  `Ring.not_isField_of_ne_of_ne`; typeclass `IsField F` is not the same object
  as the available `[Field F]` structure.

### FATEM041: Order In A Product Group

```lean
theorem fatem_041_orderOf_prod {G H : Type*} [Group G] [Group H]
    {a : G} {b : H} :
    orderOf (a, b) = Nat.lcm (orderOf a) (orderOf b)
```

- **Paper proof:** `(a,b)^k = 1` exactly when both coordinate powers are `1`;
  the least common exponent is the least common multiple.
- **Strong Lean strategy:** use `Prod.orderOf_mk` and `simpa`.
- **Expected subgoal:** alignment of the library theorem with the target.
- **API traps:** `orderOf = 0` represents infinite order; do not add finiteness
  assumptions.

### FATEM109: Left Cancellation Without Zero Divisors

```lean
theorem fatem_109_mul_left_cancel_of_NoZeroDivisors
    {R : Type*} [Ring R] [NoZeroDivisors R]
    (a b c : R) (h₁ : ¬ a = 0 ∧ a * b = a * c) : b = c
```

- **Paper proof:** rewrite as `a * (b - c) = 0`; nonzero `a` and absence of
  zero divisors imply `b - c = 0`.
- **Strong Lean strategy:** extract `h₁.1` and `h₁.2`, then use an appropriate
  `mul_left_cancel₀` lemma; use the subtraction argument only as fallback.
- **Expected subgoals:** nonzero factor and matching cancellation theorem.
- **API traps:** do not use right cancellation, division, or commutativity.

### FATEM111: Nilpotence And An Anticommutator

```lean
theorem fatem_111_commute_of_pow_two_zero (R : Type) [Ring R]
    (a : R) (h : a ^ 2 = 0) :
    ∀ x : R, Commute (a * x + x * a) a
```

- **Paper proof:** expand `(a*x + x*a)*a = a*x*a + x*a^2` and
  `a*(a*x + x*a) = a^2*x + a*x*a`; both square terms vanish.
- **Strong Lean strategy:** introduce `x`, expose the equality inside
  `Commute`, rewrite `pow_two`, distribute, reassociate without reordering, and
  simplify with `h`.
- **Expected subgoals:** one noncommutative equality after introducing `x`.
- **API traps:** `ring` assumes commutative normalization; the direction between
  `a ^ 2` and `a * a` matters. The paper strategy is sound, but the canonical
  traces do not certify a Lean proof.

### FATEM115: Transitivity Of The Inverse Relation

```lean
theorem fatem_115_transitive_iff {A : Type} (R : A → A → Prop) :
    Transitive R ↔ Transitive (fun x y => R y x)
```

- **Paper proof:** forward transitivity consumes `R z y` and `R y x` to obtain
  `R z x`; apply the same reversal in the other direction.
- **Strong Lean strategy:** `constructor`; introduce the transitivity function
  and relation hypotheses; call the function with proofs in reversed order.
- **Expected subgoals:** forward and reverse implications.
- **API traps:** `Transitive` has implicit element arguments. Replacing it with
  `IsTrans`, or defining a new local `Transitive`, changes the benchmark
  contract even if the mathematics appears equivalent.

### LeanCat001: Identity Natural Transformations Commute

```lean
theorem leancat_s0001_id_comm (α β : (𝟭 C) ⟶ (𝟭 C)) :
    α ≫ β = β ≫ α
```

- **Paper proof:** apply naturality of `α` to the component `β.app X`; because
  both functors are identities, the square is precisely componentwise
  commutativity. Extensionality finishes.
- **Strong Lean strategy:** use a packaged `NatTrans.id_comm` if its signature
  matches; otherwise `ext X` and instantiate naturality at `β.app X`.
- **Expected subgoals:** componentwise equality at each object.
- **API traps:** naturality orientation, overloaded `≫`, and category
  metavariables can obscure an otherwise valid argument.

### LeanCat002: A Left Factor Of A Monomorphism Is Monic

```lean
theorem leancat_s0002_monic_of_comp_monic
    {X Y Z : C} (g : X ⟶ Y) (f : Y ⟶ Z) [Mono (g ≫ f)] : Mono g
```

- **Paper proof:** postcompose an equality through `g` by `f`, cancel the mono
  composite `g ≫ f`, and conclude the original arrows are equal.
- **Strong Lean strategy:** first try `infer_instance`; otherwise construct the
  `Mono g` proof and use `Category.assoc` plus cancellation.
- **Expected subgoal:** typeclass synthesis or one cancellation obligation.
- **API traps:** composition is diagrammatic; the conclusion concerns the first
  factor `g`, not `f`.

### Medium LeanCat008: Free Product As Categorical Coproduct

```lean
theorem freeProdGrp_iso_coprod [HasBinaryCoproduct G H] :
    Nonempty (GrpCat.of (Monoid.Coprod G H) ≅ coprod G H)
```

- **Paper proof:** the group free product has canonical inclusions and the
  universal map induced by any pair of group homomorphisms. Therefore it is a
  colimit of the binary diagram. Any two colimits are uniquely isomorphic, so
  it is isomorphic to `coprod G H`.
- **Strong Lean strategy:** build the `BinaryCofan` with
  `GrpCat.ofHom Monoid.Coprod.inl/inr`; prove `IsColimit` using
  `Monoid.Coprod.lift`, its composition lemmas, and uniqueness; combine it with
  `coprodIsCoprod` through the colimit-uniqueness isomorphism; wrap the result in
  `Nonempty`.
- **Expected subgoals:** inclusions, universal map and its two equations,
  uniqueness, colimit-to-colimit isomorphism, final wrapper.
- **API traps:** coercions between `GrpCat` morphisms and bundled group
  homomorphisms, `GrpCat.ofHom_comp` orientation, `BinaryCofan.IsColimit.mk`,
  and the exact colimit uniqueness API.

#### Lean-Checked Mathematical Judgment

The theorem is true and both strategy families used in the medium traces are
formally completable. Two reference theorems were checked against the exact
three imports above with Lean 4.30.0 and the repository's cached Mathlib; the
offline Lean process exited with code 0.

The checked evidence file is retained as a private reference snapshot (SHA-256
`766d052f69495fc7748abc0b6ad10a8238572996935d41e374312fdd47b28822`).
`lake env lean` was blocked before compilation by sandbox Git ownership checks
on cached Mathlib; invoking the installed Lean 4.30.0 binary directly with the
same cached `.olean` paths produced the successful kernel result.

1. **Cofan/colimit route:** construct `BinaryCofan.mk` from
   `GrpCat.ofHom Monoid.Coprod.inl/inr`; use
   `BinaryCofan.IsColimit.mk`; prove the two equations with
   `Monoid.Coprod.lift_comp_inl/inr`; prove uniqueness with
   `Monoid.Coprod.lift_unique`; finish with
   `IsColimit.coconePointUniqueUpToIso` and `coprodIsCoprod`.
2. **Two-inverse-maps route:** define the free-product-to-coproduct map with
   `Monoid.Coprod.lift`, define the reverse map with `coprod.desc`, prove the
   free-product composite by `Monoid.Coprod.hom_ext`, prove the categorical
   coproduct composite by `coprod.hom_ext`, and package with `Iso.mk`.

The decisive uniqueness step is small:

```lean
apply GrpCat.hom_ext
apply Monoid.Coprod.lift_unique
· simpa [s] using congrArg (fun k : G ⟶ _ => k.hom) hG
· simpa [s] using congrArg (fun k : H ⟶ _ => k.hom) hH
```

This changes the interpretation of the failures: the dataset statement is not
wrong, and the central subgoals are not mathematically impossible. The agents
failed to reach a short available API proof.

| Trial | Strategy judgment | Actual accepted evidence | Can remaining nodes be proved? |
|---|---|---|---|
| `t0` | valid cofan plan | two inclusion definitions | yes; use `lift_unique`, then colimit uniqueness |
| `t1` | valid cofan plan | a correctly formed `BinaryCofan` | yes; its exact next node is the compiled reference `IsColimit` proof |
| `t2` | valid cofan plan | two inclusion definitions | yes; replace exploratory extensionality with `lift_unique` |
| `t3` | partially valid, then redundant | inclusions only; `IsColimit` candidate rejected for `sorry` | yes after making node 2 be `IsColimit` and node 3 only the colimit iso |
| `t4` | valid direct-map plan, with API descriptions initially swapped | both maps compile without `sorry` | yes; the compiled direct proof supplies both inverse equations and `Iso.mk` |
| `t5` | valid high-level plan, invalid ledger completion | inclusions are valid; accepted node 2 only defines the lift infrastructure | yes, but node 2 must be reopened and fully prove equations plus uniqueness |
| `t6` | partially valid, poorly decomposed | only the already available group instance | yes after deleting the low-value node and using either checked route |
| `t7` | valid direct-map plan, artifact hygiene weak | both map definitions are locally valid, but submitted theorem bodies still contain later `sorry` | yes after extracting clean map artifacts and applying the checked inverse proofs |
| `t8` | valid direct-map plan, wrong failure diagnosis | inclusions only | yes; explicitly project `GrpCat.Hom.hom` from typed `coprod.inl/inr` |
| `t9` | mathematically plausible but too coarse | only the already available group instance | yes after splitting its broad iso node into maps, equations, and packaging |

## 4. Detailed Failure Reconstructions

Phase notation is `role seq-start..seq-end (tools; successful/failed Lean
results)`. In the canonical records, incident lists come from the existing
hash-bound reviews. A successful check inside an unsuccessful trace can be a
helper or changed statement; it is not silently promoted to target success.

### 4.1 Canonical FATEM019: The Mathematical Route Exists, The API Bridge Does Not

Eight reasoners describe a mathematically plausible prime/field argument. The
implementation repeatedly invents bridges such as `IsField.toIsDomain` or
misuses `Fact (Nat.Prime n)`. Trials `t5` and `t7` never finish retrieval. No
trial reaches a critic. The task-level pattern is therefore **reasoner/API
misalignment**, not evidence that the theorem or dataset statement is false.

#### `canonical/easy_fatem_019_t0`

- **Strategy comparison:** `valid_strategy`; the reasoner proposes prime field
  instances and a reverse no-zero-divisor argument, aligned at paper level.
- **Phases:** `R 1..23` makes 11 searches and hands off; `E 24..28` makes one
  failed check and two further searches.
- **Failure chain:** `s24 opaque_compiler_failure U`. The result contains no
  usable diagnostic, so the critical cause is `tooling_diagnostic_unknown`, not
  a mathematical error. No critic appears; final trust is **do not trust**.

#### `canonical/easy_fatem_019_t1`

- **Strategy comparison:** `valid_strategy`; it tries `IsDomain` plus finiteness
  for one direction.
- **Phases:** `R 1..15` performs seven searches; `E 16..28` performs two failed
  checks and five searches.
- **Failure chain:** `s16 unknown_symbol U -> s26 unknown_symbol U`. The first
  diagnostic says the environment has no projection `IsField.toIsDomain`.
  This is an API/library hallucination and elaboration failure. Critic missing;
  **do not trust**.

#### `canonical/easy_fatem_019_t2`

- **Strategy comparison:** `valid_strategy`, but it drifts toward ideal
  quotient machinery without a verified bridge to the target.
- **Phases:** `R 1..17` makes eight searches; `E 18..28` makes four checks and
  two searches, with one success and three failures.
- **Failure chain:** `s22 application_type_mismatch U -> s26
  opaque_compiler_failure U -> s28 opaque_compiler_failure U`. At `s22`, an
  `IsField (ZMod n)` term is supplied where `Nat.Prime n` is expected. The
  successful check does not recover the exact target. Critic missing; **do not
  trust**.

#### `canonical/easy_fatem_019_t3`

- **Strategy comparison:** `valid_strategy`; quotient-prime reasoning is
  plausible, but the proposed projection is not in the API.
- **Phases:** `R 1..17` makes eight searches; `E 18..28` makes two failed checks
  and four searches.
- **Failure chain:** `s18 unknown_symbol U -> s28
  application_type_mismatch U`. Critical event `s18` again uses the nonexistent
  `IsField.toIsDomain`. No critic; **do not trust**.

#### `canonical/easy_fatem_019_t4`

- **Strategy comparison:** `valid_strategy`; it identifies `ZMod.instField`
  but never validates the reverse proposition/typeclass conversion.
- **Phases:** `R 1..17` makes eight searches; `E 18..28` makes two failed checks
  and four searches.
- **Failure chain:** `s18 unknown_symbol U -> s26
  application_type_mismatch U`. The first unrecovered failure is the same
  nonexistent `IsField.toIsDomain` bridge. No critic; **do not trust**.

#### `canonical/easy_fatem_019_t5`

- **Strategy comparison:** `no_real_strategy`.
- **Phases:** `R 1..25` performs 12 searches and never calls the engineer.
- **Failure chain:** `s25 target_not_attempted U`. This is retrieval
  perseveration by outcome, although the existing repeated-code detector does
  not flag varied search queries. No engineer or critic; **do not trust**.

#### `canonical/easy_fatem_019_t6`

- **Strategy comparison:** `valid_strategy`; it correctly notices that a
  `Fact (Nat.Prime n)` instance is needed.
- **Phases:** `R 1..21` makes ten searches; `E 22..28` makes one failed check
  and three searches.
- **Failure chain:** `s22 typeclass_resolution U`: Lean expected an
  `IsField (ZMod n)` instance. The strategy does not resolve which direction
  supplies which instance. No critic; **do not trust**.

#### `canonical/easy_fatem_019_t7`

- **Strategy comparison:** `no_real_strategy`.
- **Phases:** `R 1..15` performs seven searches with no handoff.
- **Failure chain:** `s15 target_not_attempted U`. No candidate, engineer, or
  critic evidence exists; **do not trust**.

#### `canonical/easy_fatem_019_t8`

- **Strategy comparison:** `valid_strategy`; it names the prime `Fact` bridge
  but does not implement both directions.
- **Phases:** `R 1..17` makes eight searches; `E 18..28` makes three checks and
  three searches, with one success and two failures.
- **Failure chain:** `s18 unknown_symbol U -> s22 sorry_pseudo_pass U -> s24
  opaque_compiler_failure U`. A helper containing `sorry` cannot be recovery.
  Critical event `s18` again names `IsField.toIsDomain`. No critic; **do not
  trust**.

#### `canonical/easy_fatem_019_t9`

- **Strategy comparison:** `valid_strategy`; it proposes the standard prime
  instance route.
- **Phases:** `R 1..23` makes 11 searches; `E 24..28` makes one failed check and
  two searches.
- **Failure chain:** `s24 unknown_symbol U`, again the invalid
  `IsField.toIsDomain` projection. No critic; **do not trust**.

### 4.2 Canonical FATEM020: Correct Field Intuition, Wrong Typeclass Interface

The successful trials show the task is solvable in the pinned environment. In
the seven failed trials, most reasoners choose a contrapositive based on
`Ring.not_isField_of_ne_of_ne`; the engineers then repeatedly ask Lean for an
`IsField F` object that is not supplied by the target's `[Field F]` assumption.
The repeated local error is not evidence of an infrastructure import failure.

#### `canonical/easy_fatem_020_t2`

- **Strategy comparison:** `valid_strategy` at paper level, but tied to the
  wrong library interface.
- **Phases:** `R 1..3` makes one search; `E 4..16` makes six failed checks and
  one search.
- **Failure chain:** `s4 typeclass_resolution U -> s6
  application_type_mismatch U -> s8 application_type_mismatch U -> s12
  typeclass_resolution U -> s14 typeclass_resolution U -> s16
  typeclass_resolution U`. Critical `s4` expects `IsField F`. No critic;
  **do not trust**.

#### `canonical/easy_fatem_020_t3`

- **Strategy comparison:** `no_real_strategy`.
- **Phases:** `R 1..11` makes five searches and never hands off.
- **Failure chain:** `s11 target_not_attempted U`. No candidate or critic;
  **do not trust**.

#### `canonical/easy_fatem_020_t4`

- **Strategy comparison:** `valid_strategy`, again using the contrapositive
  field characterization without a type-correct application plan.
- **Phases:** `R 1..5` makes two searches; `E 6..28` makes six failed checks and
  six searches.
- **Failure chain:** `s6 typeclass_resolution U -> s8
  typeclass_resolution U -> s10 typeclass_resolution U -> s14 unknown_symbol U
  -> s26 opaque_compiler_failure U -> s28 opaque_compiler_failure U`. Critical
  `s6` is the unresolved `IsField F` expectation. No critic; **do not trust**.

#### `canonical/easy_fatem_020_t5`

- **Strategy comparison:** `valid_strategy` at paper level.
- **Phases:** `R 1..3` makes one search; `E 4..14` makes six failed checks.
- **Failure chain:** `s4 typeclass_resolution U -> s6 typeclass_resolution U ->
  s8 application_type_mismatch U -> s10 typeclass_resolution U -> s12
  opaque_compiler_failure U -> s14 typeclass_resolution U`. No strategy
  revision or critic; **do not trust**.

#### `canonical/easy_fatem_020_t7`

- **Strategy comparison:** `valid_strategy`, but no API correction after the
  first typeclass failure.
- **Phases:** `R 1..3` makes one search; `E 4..16` makes six failed checks and
  one search.
- **Failure chain:** `s4 typeclass_resolution U -> s8 typeclass_resolution U ->
  s10 typeclass_resolution U -> s12 typeclass_resolution U -> s14
  opaque_compiler_failure U -> s16 typeclass_resolution U`. No critic;
  **do not trust**.

#### `canonical/easy_fatem_020_t8`

- **Strategy comparison:** `valid_strategy`; the engineer performs the most
  exploration but does not preserve a successful exact target.
- **Phases:** `R 1..3` makes one search; `E 4..28` makes 12 checks and one
  search, with five successes and seven failures.
- **Failure chain:** `s4, s8, s12, s14, s20, s22 typeclass_resolution U -> s28
  unknown_symbol U`. The five successes are helper/process evidence because no
  exact target is accepted. No critic; **do not trust**.

#### `canonical/easy_fatem_020_t9`

- **Strategy comparison:** `valid_strategy`; the reasoner explicitly proposes
  `Ring.not_isField_of_ne_of_ne`.
- **Phases:** `R 1..5` makes two searches; `E 6..16` makes six failed checks.
- **Failure chain:** `s6 application_type_mismatch U -> s8, s10, s12
  typeclass_resolution U -> s14 opaque_compiler_failure U -> s16
  typeclass_resolution U`. At `s6`, a negated disjunction is supplied where a
  proof of `I ≠ ⊤` is expected. No critic; **do not trust**.

### 4.3 Canonical FATEM109: Search Without A Plan

Eight canonical trials solve the cancellation theorem. The two failures do not
reach formalization at all.

#### `canonical/easy_fatem_109_t3`

- **Strategy comparison:** `no_real_strategy`.
- **Phases:** `R 1..23` makes 12 searches, with no handoff or check.
- **Failure chain:** `s23 target_not_attempted U`. The failure is reasoner
  stopping/retrieval behavior, not Lean typing. **Do not trust**.

#### `canonical/easy_fatem_109_t9`

- **Strategy comparison:** `no_real_strategy`.
- **Phases:** `R 1..5` makes two searches and stops.
- **Failure chain:** `s5 target_not_attempted U`. No engineer or critic;
  **do not trust**.

### 4.4 Canonical FATEM111: Sound Algebra, Failed Formalization

All ten reasoners identify the same valid paper calculation: expand both sides
without commuting factors and remove the `a^2` terms. The canonical system
therefore does not fail first at mathematical strategy. It fails while exposing
`Commute`, matching `a ^ 2` with `a * a`, and choosing tactics compatible with a
noncommutative ring. Many tool responses are opaque, so attribution beyond the
visible tactic failures must remain `not_observable`.

#### `canonical/easy_fatem_111_t0`

- **Strategy comparison:** `valid_strategy`; direct noncommutative expansion.
- **Phases:** `R 1..11` makes five searches; `E 12..28` makes nine checks, one
  successful and eight failed.
- **Failure chain:** `s12 opaque U -> s14 opaque U -> s16 tactic_failure U ->
  s18 opaque U -> s20 opaque U -> s24 opaque U -> s26 opaque U -> s28 opaque
  U`. The one success is not an accepted target. No critic; **do not trust**.

#### `canonical/easy_fatem_111_t1`

- **Strategy comparison:** `valid_strategy`; it writes both expanded sides
  correctly.
- **Phases:** `R 1..7` makes three searches; `E 8..18` makes six failed checks.
- **Failure chain:** `s8 opaque U -> s10 opaque U -> s12 tactic_failure U ->
  s14 opaque U -> s16 tactic_failure U -> s18 opaque U`. No critic; **do not
  trust**.

#### `canonical/easy_fatem_111_t2`

- **Strategy comparison:** `valid_strategy`; correct factor order and use of
  nilpotence.
- **Phases:** `R 1..9` makes four searches; `E 10..20` makes six failed checks.
- **Failure chain:** `s10, s12, s14, s16, s18 opaque U -> s20 unknown_symbol
  U`. The final API guess also fails. No critic; **do not trust**.

#### `canonical/easy_fatem_111_t3`

- **Strategy comparison:** `valid_strategy`.
- **Phases:** `R 1..9` makes four searches; `E 10..20` makes six failed checks.
- **Failure chain:** `s10 opaque U -> s12 opaque U -> s14 tactic_failure U ->
  s16 opaque U -> s18 tactic_failure U -> s20 tactic_failure U`. No critic;
  **do not trust**.

#### `canonical/easy_fatem_111_t4`

- **Strategy comparison:** `valid_strategy`.
- **Phases:** `R 1..7` makes three searches; `E 8..18` makes six failed checks.
- **Failure chain:** `s8, s10, s12, s14, s16, s18 opaque_compiler_failure U`.
  There is not enough diagnostic text to distinguish syntax, elaboration, and
  tactic causes. No critic; **do not trust**.

#### `canonical/easy_fatem_111_t5`

- **Strategy comparison:** `valid_strategy`.
- **Phases:** `R 1..11` makes five searches; a message-only `E 12 -> R 13 -> E
  14` reentry occurs without an explicit evidence-bearing route; `E 14..24`
  then makes six failed checks.
- **Failure chain:** `s14, s16, s18, s20 opaque U -> s22 tactic_failure U ->
  s24 tactic_failure U`. The non-chain graph reflects the reentry, not a
  productive strategy revision. No critic; **do not trust**.

#### `canonical/easy_fatem_111_t6`

- **Strategy comparison:** `valid_strategy`.
- **Phases:** `R 1..7` makes three searches; `E 8..18` makes six failed checks.
- **Failure chain:** all six checks at `s8, s10, s12, s14, s16, s18` are opaque
  unrecovered failures. No critic; **do not trust**.

#### `canonical/easy_fatem_111_t7`

- **Strategy comparison:** `valid_strategy`.
- **Phases:** `R 1..9` makes four searches; `E 10..20` makes six failed checks.
- **Failure chain:** `s10 opaque U -> s12 opaque U -> s14 tactic_failure U ->
  s16 opaque U -> s18 opaque U -> s20 tactic_failure U`. No critic; **do not
  trust**.

#### `canonical/easy_fatem_111_t8`

- **Strategy comparison:** `valid_strategy`.
- **Phases:** `R 1..7` makes three searches; `E 8..18` makes six failed checks.
- **Failure chain:** all six checks are opaque unrecovered failures. No critic;
  **do not trust**.

#### `canonical/easy_fatem_111_t9`

- **Strategy comparison:** `valid_strategy`.
- **Phases:** `R 1..11` makes five searches; a message-only `E 12 -> R 13 -> E
  14` reentry precedes six failed checks at `E 14..24`.
- **Failure chain:** `s14 opaque U -> s16 opaque U -> s18, s20, s22
  tactic_failure U -> s24 opaque U`. As in `t5`, role reentry does not lead to a
  revised formalization strategy. No critic; **do not trust**.

### 4.5 Canonical FATEM115: Local Type Failure Becomes Statement Drift

The direct proof is short, but `Transitive` takes implicit element arguments.
Engineers repeatedly call the transitivity hypothesis as if all elements were
explicit. Four runs escape that local typing problem by replacing `Transitive`
with `IsTrans` or another changed definition. Those artifacts may compile, but
they do not preserve the supplied declaration. This is the clearest interaction
between engineer drift and critic failure.

#### `canonical/easy_fatem_115_t0`

- **Strategy comparison:** `partially_valid_strategy`; the relation reversal is
  right, but the application plan treats `Transitive` arguments incorrectly.
- **Phases:** `R 1..7` makes three searches; `E 8..24` makes six failed checks
  and three searches.
- **Failure chain:** `s8 application_type_mismatch U -> s12
  application_type_mismatch U -> s16 tactic_failure U -> s18, s22, s24
  application_type_mismatch U`. No critic; **do not trust**.

#### `canonical/easy_fatem_115_t1`

- **Strategy comparison:** `valid_strategy` mathematically.
- **Phases:** `R 1..5` makes two searches; `E 6..20` makes six failed checks and
  two searches.
- **Failure chain:** `s6 application_type_mismatch U -> s10 tactic_failure U ->
  s12, s16, s18, s20 application_type_mismatch U`. No critic; **do not trust**.

#### `canonical/easy_fatem_115_t2`

- **Outcome:** silent failure and the only canonical trace with trace-internal
  critic masking.
- **Strategy comparison:** `partially_valid_strategy`; the proof idea is right,
  but formalization changes the contract.
- **Phases:** `R 1..5` makes two searches; `E 6..20` makes five checks and two
  searches with one success/four failures, then routes to critic; `C 21..25`
  makes two checks with one success/one failure and approves.
- **Failure chain:** recovered `s6 application_type_mismatch R -> s10
  tactic_failure R -> s12 application_type_mismatch R -> s14
  application_type_mismatch R`; unrecovered `s21 statement_drift U -> s23
  tactic_failure U -> s25 critic_approval_after_failed_recheck U`.
- **Critical point:** at `s21` the critic checks and accepts a changed theorem;
  its later exact-target recheck fails, yet approval follows. **Do not trust**.

#### `canonical/easy_fatem_115_t3`

- **Strategy comparison:** `partially_valid_strategy`.
- **Phases:** `R 1..5` makes two searches; `E 6..28` makes nine checks and three
  searches, with six successes and three failures.
- **Failure chain:** `s6 application_type_mismatch R -> s10 tactic_failure R ->
  s14 statement_drift U -> s18 tactic_failure U`. The compiled changed theorem
  is the first unrecovered incident; no critic accepts it. **Do not trust**.

#### `canonical/easy_fatem_115_t4`

- **Strategy comparison:** `valid_strategy` at the narrative level.
- **Phases:** `R 1..7` makes three searches; `E 8..10` gets one success and
  routes to critic; `C 11..13` recompiles successfully and approves.
- **Failure chain:** `s11 statement_drift U`. Both successful checks concern the
  changed declaration, so agreement between engineer and critic does not repair
  fidelity. **Do not trust**.

#### `canonical/easy_fatem_115_t5`

- **Strategy comparison:** `valid_strategy` mathematically.
- **Phases:** `R 1..5` makes two searches; `E 6..20` makes six checks and one
  search with two successes/four failures; `C 21..23` recompiles and approves.
- **Failure chain:** recovered `s6 application_type_mismatch R -> s10
  tactic_failure R -> s12, s14 application_type_mismatch R`; unrecovered `s21
  statement_drift U`. The critic validates the wrong contract. **Do not trust**.

#### `canonical/easy_fatem_115_t6`

- **Strategy comparison:** `valid_strategy` mathematically.
- **Phases:** `R 1..5` makes two searches; `E 6..20` makes six failed checks and
  two searches.
- **Failure chain:** `s6, s10 application_type_mismatch U -> s12 tactic_failure
  U -> s14 application_type_mismatch U -> s18, s20 typeclass_resolution U`.
  No critic; **do not trust**.

#### `canonical/easy_fatem_115_t7`

- **Strategy comparison:** `partially_valid_strategy`.
- **Phases:** `R 1..5` makes two searches; `E 6..8` makes one failed check; the
  trace returns to `R 9..11` for one search but never returns to engineering.
- **Failure chain:** `s6 application_type_mismatch U`. The role return is not a
  completed repair loop. No critic; **do not trust**.

#### `canonical/easy_fatem_115_t8`

- **Strategy comparison:** `partially_valid_strategy`.
- **Phases:** `R 1..5` makes two searches; `E 6..20` makes six checks and one
  search with one success/five failures; `C 21..23` recompiles and approves.
- **Failure chain:** recovered `s6 application_type_mismatch R -> s10
  tactic_failure R -> s12 tactic_failure R -> s14, s16
  application_type_mismatch R`; unrecovered `s21 statement_drift U`. **Do not
  trust**.

#### `canonical/easy_fatem_115_t9`

- **Strategy comparison:** `partially_valid_strategy`.
- **Phases:** `R 1..5` makes two searches; `E 6..20` makes six failed checks and
  two searches.
- **Failure chain:** `s6 application_type_mismatch U -> s10 tactic_failure U ->
  s12, s14, s18 application_type_mismatch U -> s20 type_mismatch U`. No critic;
  **do not trust**.

### 4.6 Canonical LeanCat001: Naturality Is Understood, Elaboration Is Fragile

All four failed reasoners identify the correct naturality/extensionality route.
The traces do not preserve enough compiler text for confident root-cause labels
in most attempts. Successful helper checks in `t0` and `t6` do not become an
accepted exact target.

#### `canonical/easy_leancat_001_t0`

- **Strategy comparison:** `valid_strategy`; componentwise naturality.
- **Phases:** `R 1..9` makes four searches; `E 10..28` makes nine checks and one
  search, with two successes/seven failures.
- **Failure chain:** opaque unrecovered failures at `s10, s12, s16, s22, s24,
  s26, s28`. No critic; **do not trust**.

#### `canonical/easy_leancat_001_t3`

- **Strategy comparison:** `valid_strategy`; it correctly specializes
  naturality to `β.app X`.
- **Phases:** `R 1..11` makes five searches; `E 12..26` makes six failed checks
  and two searches.
- **Failure chain:** opaque unrecovered failures at `s12, s14, s18, s20, s24,
  s26`. No critic; **do not trust**.

#### `canonical/easy_leancat_001_t5`

- **Strategy comparison:** `valid_strategy`; extensionality plus naturality.
- **Phases:** `R 1..11` makes five searches; `E 12..22` makes six failed checks.
- **Failure chain:** opaque failures at `s12, s14, s16, s20, s22` and
  `typeclass_resolution` at `s18`. Critical `s12` remains unobservable. No
  critic; **do not trust**.

#### `canonical/easy_leancat_001_t6`

- **Strategy comparison:** `valid_strategy`.
- **Phases:** `R 1..7` makes three searches; `E 8..28` makes eight checks and
  three searches, with five successes/three failures.
- **Failure chain:** opaque unrecovered failures at `s14, s16, s26`. The five
  successes do not yield an accepted target or critic handoff. **Do not trust**.

### 4.7 Canonical LeanCat002: Retrieval Never Becomes A Plan

#### `canonical/easy_leancat_002_t1`

- **Strategy comparison:** `no_real_strategy`, unlike the other nine successful
  trials which find the mono-instance or cancellation route.
- **Phases:** `R 1..11` makes six searches and stops.
- **Failure chain:** `s11 target_not_attempted U`. No engineer or critic;
  **do not trust**.

### 4.8 Recovery-Prompt Failures: More Instructions, The Same One-Way Route

All ten recovery traces are causal chains. Across the cohort there are nine
reasoner-to-engineer routes, eight engineer-to-critic routes, and no
engineer-to-reasoner or critic-to-engineer route. The prompt changes language,
but it does not create a recovery loop.

#### `recovery/easy_fatem_012_t0`

- **Historical summary:** `silent_failure`. **Current report status:**
  `validation_unknown`, because the fresh strict audit produced no verdict.
- **Strategy comparison:** aligned. The reasoner chooses `Int.castRingHom R` and
  uniqueness through `Subsingleton (ℤ →+* R)`.
- **Phases:** `R 1..5` makes two searches and routes to engineer; `E 6..20`
  makes seven target-like checks with five failures and two identical final
  successes; `C 21` approves without recompiling.
- **Failure mechanics:** the engineer repairs malformed uses of
  `RingHom.Int.subsingleton_ringHom`; the final in-loop exact declaration is
  sorry-free and compiled. The trace supports **productive local repair** but
  not a freshly reconfirmed independent kernel verdict. The historical silent
  label should not be interpreted as a newly observed false proof.

#### `recovery/easy_fatem_019_t0`

- **Historical summary:** unsolved.
- **Strategy comparison:** no completed strategy.
- **Phases:** `R 1..27` performs 14 searches. Engineer and critic are never
  called; no Lean candidate exists.
- **Critical failure:** target not attempted. The varied queries evade the
  identical-code perseveration detector, but behaviorally this is a retrieval
  stall. **Do not trust**.

#### `recovery/easy_fatem_109_t0`

- **Historical summary:** `silent_failure`. **Current report status:**
  `validation_unknown` after the unavailable fresh audit.
- **Strategy comparison:** strongly aligned. The reasoner identifies
  `mul_left_cancel₀`, extracts nonzero `a`, and uses the product equality.
- **Phases:** `R 1..7` makes three searches; `E 8..10` compiles the exact target;
  `C 11..13` recompiles the same target and approves. Both checks succeed.
- **Interpretation:** the raw trace does not show a false proof or statement
  drift. The discrepancy is between a historical summary label and currently
  unavailable independent revalidation. Report it as a scoring/provenance
  uncertainty, not as an agent mathematical failure.

#### `recovery/easy_fatem_115_t0`

- **Historical summary:** unsolved.
- **Strategy comparison:** paper-level relation reversal is aligned, but the
  implementation again struggles with implicit `Transitive` arguments.
- **Phases:** `R 1..5` makes two searches; `E 6..28` makes 11 checks and one
  search, with six successes/five failures. It never routes to critic.
- **Failure mechanics:** failed attempts include tactic, application, and type
  mismatches. The six successes are not a completed, critic-reviewed exact
  submission. The engineer performs local exploration but does not close the
  workflow. **Do not trust**.

### 4.9 Tool-Routed FATEM115: Communication Increases, Fidelity Still Fails

The typed subgoal experiment creates real critic-to-engineer returns and makes
candidate purpose visible. It still produces three serial event chains. This
is evidence that communication count and correctness are different variables.

#### `tool-routed/easy_fatem_115_t0`

| Seq range | Role | Purpose | Action and evidence | Interpretation |
|---|---|---|---|---|
| 1..11 | Reasoner | planning | Defines three subgoals, reads the ledger, routes to engineer | Decomposition exists but contains no completed strategy message |
| 13..21 | Engineer | forward subgoal | Three `purpose=subgoal` checks; all fail; two searches | Application mismatch followed by invalid/uncertain API attempts |
| 23 | Reasoner | forced recovery | Runtime returns control after failure limit | No revised candidate follows |

- **Outcome:** unsolved; zero accepted subgoals and no critic review.
- **Critical failure:** the forward-direction candidate never becomes
  type-correct. The forced return changes the speaker but not the mathematical
  state. **Do not trust**.

#### `tool-routed/easy_fatem_115_t1`

| Seq range | Role | Purpose | Action and evidence | Interpretation |
|---|---|---|---|---|
| 1..9 | Reasoner | planning | Three subgoals and route to engineer | Concrete decomposition |
| 11..19 | Engineer | forward subgoal | Three failed candidates, including a hallucinated import | First repair cycle exhausted |
| 21..25 | Reasoner | revision | Search, revise plan, route back | Evidence-triggered revision |
| 27..33 | Engineer | forward subgoal | Three more failures | Revised plan still lacks correct API use |
| 35..37 | Reasoner | revision | Revises and routes again | Second forced recovery |
| 39..57 | Engineer | subgoal work | Three failures, two compiled candidates, submissions and routes | Local progress but no accepted ledger node |
| 59..71 | Critic | review | Three successful reviews, then rejects and routes back | Critic uses evidence and refuses completion |
| 73..79 | Engineer/critic | repair | One compiled candidate submitted; critic reads state | Trace ends before acceptance or final integration |

- **Outcome:** unsolved. Seven failed and six successful compiler results; three
  critic rechecks; one rejection; no accepted subgoal.
- **Failure mechanics:** this is a genuine communication loop, but the state
  does not cross the acceptance gate. It is better observed than the canonical
  runs, not more successful. **Do not trust**.

#### `tool-routed/easy_fatem_115_t2`

| Seq range | Role | Purpose | Action and evidence | Interpretation |
|---|---|---|---|---|
| 1..9 | Reasoner | planning | Three subgoals and route | Decomposition is concrete |
| 11..17 | Engineer | forward subgoal | Three failures | Implicit-argument/import failures |
| 19..23 | Reasoner | revision | Revises plan and routes | Evidence-backed recovery attempt |
| 25..41 | Engineer | forward subgoal | Two failures, two successes, submission | Candidate now compiles |
| 43..59 | Critic/engineer | reviews | Two subgoals reviewed and accepted through returns | Real critic-engineer interaction |
| 61..67 | Engineer | final | Two `purpose=final` checks compile | Runtime sees an integrated candidate |
| 69..73 | Critic | final review | Review compiles; `finish_run` succeeds | Runtime declares verified completion |

- **Historical summary:** silent failure. Raw code explains why: the candidate
  first defines its own `Transitive`, shadowing the supplied Mathlib predicate,
  and then proves the theorem under that changed environment.
- **Failure mechanics:** three subgoals are accepted and the runtime completion
  gate passes, but statement fidelity fails. More gates do not help when every
  gate evaluates the same altered contract. **Do not trust**.

#### `tool-routed-aborted/easy_fatem_115_t0`

| Seq range | Role | Purpose | Action and evidence | Interpretation |
|---|---|---|---|---|
| 1..9 | Reasoner | planning | Three subgoals and route | Plan established |
| 11..17 | Engineer | forward subgoal | Three failed checks | Initial implementation failure |
| 19..23 | Reasoner | revision | Revises and routes | One evidence-backed recovery |
| 25..41 | Engineer | subgoal | Two failures, one success and submission | One candidate reaches review |
| 43..46 | Critic/tool runtime (legacy executor label) | review | Review compiles and one subgoal is accepted | Trace stops before a decision about later subgoals |

- **Outcome:** interrupted snapshot, not unsolved completion. It has five failed
  and two successful results, one accepted subgoal, and no terminal event.
- **Trust:** insufficient evidence. Interruption must not be converted into a
  mathematical failure.

### 4.10 Medium LeanCat008: Ten Completed Trials, One Stable Boundary

The domain strategy is to make the free product into a `BinaryCofan`, prove its
`IsColimit` property using `Monoid.Coprod.lift`, and invoke uniqueness of
colimits against `coprodIsCoprod`. A second valid route constructs morphisms in
both directions and proves the two composites are identities. The ten reasoners
mostly choose one of these routes. Their shared weakness is not the informal
mathematics; it is expressing uniqueness and composition through the exact
`GrpCat`, `BinaryCofan`, and `Monoid.Coprod` APIs.

All ten trials terminate and all ten are unsolved. Seven reach the turn cap and
three stop as `stuck`. They define 42 subgoals and accept 13, but never record a
verified completion. The critic performs 19 successful recompilations, accepts
13 candidates, and rejects six incomplete or `sorry`-bearing candidates. Thus
the critic is stricter than in the canonical FATEM115 failures, but it only
guards submitted nodes; it cannot repair long intervals in which no candidate
is submitted.

Mathematical audit separates those 13 acceptances into three levels: 13 ledger
acceptances, 12 locally valid subgoal constructions (all except `t5` node 2),
and ten clean whole artifacts (excluding the two `t7` theorem bodies that retain
later `sorry`). These counts describe different evidence contracts.

| Trial | Terminal | Events | Accepted | Final active work | Searches | Compile ok/fail | E->R / C->E | Longest path |
|---|---|---:|---:|---|---:|---:|---:|---:|
| `t0` | cap | 202 | 1 | universal property | 47 | 17/21 | 1/2 | 142 |
| `t1` | cap | 202 | 1 | `IsColimit` | 22 | 44/25 | 0/1 | 201 |
| `t2` | stuck | 147 | 1 | `IsColimit` | 19 | 24/17 | 0/1 | 146 |
| `t3` | cap | 202 | 1 | revised universal/iso node | 27 | 22/24 | 3/2 | 126 |
| `t4` | cap | 202 | 2 | first inverse equation | 20 | 12/47 | 3/2 | 170 |
| `t5` | cap | 202 | 2 | iso integration | 28 | 26/24 | 1/4 | 193 |
| `t6` | cap | 202 | 1 | first substantive morphism | 68 | 10/8 | 1/1 | 115 |
| `t7` | stuck | 151 | 2 | first inverse equation | 20 | 25/10 | 0/4 | 150 |
| `t8` | stuck | 116 | 1 | map to categorical coproduct | 17 | 14/10 | 2/1 | 88 |
| `t9` | cap | 202 | 1 | universal/direct iso | 74 | 10/2 | 0/1 | 100 |

Compiler totals exclude one unresolved call in `t1` and malformed tool-argument
results in `t2` and `t7`; those two executions return JSON parsing errors rather
than Lean verdicts.

#### `medium/medium_leancat_008_t0`

| Seq range | Role | Purpose | Action and evidence | Interpretation |
|---|---|---|---|---|
| 1..21 | Reasoner | retrieval and planning | Six searches; four subgoals; route to engineer | Paper strategy aligned: inclusions, universal property, colimit iso, wrapper |
| 23..37 | Engineer | subgoal 1 | Five probes and one subgoal candidate; four probe successes, one probe failure, subgoal compiles | Inclusion artifact implemented |
| 39..45 | Critic | subgoal 1 review | Review compiles and accepts | First mathematical milestone verified |
| 47..99 | Engineer | subgoal 2 | Eight probes, ten subgoal attempts, nine searches; all ten subgoal attempts fail | Universal-property proof becomes the bottleneck |
| 101..155 | Reasoner/engineer/critic | revision | One forced plan revision; many searches; one later subgoal candidate and critic review | Some evidence-backed recovery, but critic rejects the candidate because it is incomplete/contains prohibited evidence |
| 157..199 | Engineer | subgoal 2 retry | 12 searches, five subgoal failures, five probes | Returns to local trial-and-error without closing uniqueness |
| 200..201 | System | termination | Controller records final plan and `cap` at 200 turns | Later subgoals never activate |

- **Counts:** 47 searches; 13/6 successful/failed probes; 2/15 successful/failed
  subgoal checks; two successful reviews; 21 total failures.
- **Plan state:** subgoal 1 accepted; subgoal 2 active after 16 attempts and five
  consecutive failures; subgoals 3 and 4 pending; one forced recovery and one
  strategy revision.
- **Communication:** `R->E=1`, `E->R=1`, `C->E=2`; this is the first explicit
  engineer-to-reasoner return in the medium batch.
- **Critical failure:** the strategy is valid but the engineer cannot prove the
  universal-map equations and uniqueness with the exact `GrpCat`/`Coprod` API.
  Termination is a turn cap, not a kernel rejection. **Do not trust as a final
  proof**.

#### `medium/medium_leancat_008_t1`

| Seq range | Role | Purpose | Action and evidence | Interpretation |
|---|---|---|---|---|
| 1..27 | Reasoner | retrieval and planning | Nine searches; four sequential subgoals | Aligned decomposition |
| 29..73 | Engineer | subgoal 1 | 18 probes and three subgoal candidates; 17 probe successes; one candidate accepted after repair | Inclusion cofan established |
| 75..81 | Critic | subgoal 1 review | Review compiles; route back to engineer | One accepted milestone |
| 83..199 | Engineer | subgoal 2 | 44 probes, four subgoal attempts, 11 searches | Long API exploration with no accepted universal-property artifact |
| 200..201 | System | termination | `cap` at 200 turns | Subgoals 3 and 4 never start |

- **Counts:** 22 searches; 42/20 successful/failed probes; 1/5
  successful/failed subgoal checks; one successful review. Of 44 successful
  compiler results, 42 are probes.
- **Plan state:** subgoal 1 accepted after three attempts; subgoal 2 active after
  three failed candidates; no forced recovery or strategy revision.
- **Communication:** one reasoner-to-engineer and one critic-to-engineer route,
  but no reasoner reentry after the long failure sequence.
- **Critical failure:** probe accumulation replaces strategy revision. The run
  discovers many signatures but does not turn them into the uniqueness proof.
  **Do not trust as a final proof**.

#### `medium/medium_leancat_008_t2`

| Seq range | Role | Purpose | Action and evidence | Interpretation |
|---|---|---|---|---|
| 1..29 | Reasoner | retrieval and planning | Seven searches; four subgoals; three plan revisions before work begins | More precise decomposition than `t0/t1` |
| 30..51 | Engineer/critic | subgoal 1 | Six checks; candidate and review compile; accepted | Inclusion morphisms verified |
| 52..143 | Engineer | uniqueness exploration | 11 searches and 35 checks; 17 failures | `liftEquiv`, coercions, rewrites, and extensionality never become a candidate |
| 144..146 | Tool runtime/system (legacy executor label) | malformed call and stop | Final check returns an unterminated-JSON argument error; `stuck` at turn 145 | Tool-format failure is not a Lean verdict |

- **Counts:** 19 searches; probes 22/17; subgoals 1/0; reviews 1/0.
- **Final plan:** inclusions accepted; `IsColimit` active with zero submitted
  attempts; iso and wrapper pending.
- **Communication:** `R->E=1`, `E->R=0`, `C->E=1`.
- **Critical failure:** the engineer repeatedly describes the correct uniqueness
  idea but uses unknown or ill-oriented API operations. Because it never submits
  subgoal 2, the critic cannot intervene. `stuck` is a routing termination, not
  proof evidence.

#### `medium/medium_leancat_008_t3`

| Seq range | Role | Purpose | Action and evidence | Interpretation |
|---|---|---|---|---|
| 1..43 | Reasoner/engineer/critic | plan and inclusions | Four nodes; first candidate accepted | Normal initial progress |
| 44..113 | Engineer | universal property | 14 searches, 20 checks, 12 failures | Exact API bridge remains unresolved |
| 114..173 | Engineer/reasoner | repeated recovery | Three engineer returns, four reasoner-to-engineer routes, two plan revisions | Communication increases, but strategy oscillates between direct iso and `IsColimit` |
| 174..199 | Engineer/critic | final attempt | Five checks; candidate compiles with `sorry`; critic rejects | Gate prevents false subgoal acceptance |
| 200..201 | System | termination | `cap` | Only first node accepted |

- **Counts:** 27 searches; probes 18/11; subgoals 2/13; reviews 2/0.
- **Final plan:** first node accepted; revised universal/iso node active after 14
  attempts; two nodes pending; one forced recovery and two revisions.
- **Communication:** `R->E=4`, `E->R=3`, `C->E=2`, 16 tool handoffs.
- **Critical failure:** return communication carries compiler evidence, but each
  revision rephrases the same unclosed uniqueness obligation. This is
  communication without a new executable invariant.

#### `medium/medium_leancat_008_t4`

| Seq range | Role | Purpose | Action and evidence | Interpretation |
|---|---|---|---|---|
| 1..25 | Reasoner | direct inverse plan | Five nodes: construct `f`, construct `g`, prove both identities, package iso | Valid alternative to the cofan route |
| 26..83 | Engineer/critic | two morphisms | 18 checks for `f`, then one for `g`; both reviewed and accepted | Furthest clean decomposition before equations |
| 84..145 | Engineer | first identity | 22 checks, 21 failures | `coprod.hom_ext` and composition simplification fail |
| 146..199 | Engineer/reasoner | retries | Three returns to reasoner, one revision, 17 more failed checks | Revision arrives at the cap and does not execute |
| 200..201 | System | termination | `cap` | Second identity and iso remain pending |

- **Counts:** 20 searches; probes 8/35; subgoals 2/12; reviews 2/0.
- **Final plan:** `f` and `g` accepted; identity node active after nine attempts;
  second identity and packaging pending.
- **Communication:** `R->E=1`, `E->R=3`, `C->E=2`.
- **Critical failure:** the agent reaches the right extensionality obligation but
  cannot normalize composites through `GrpCat.ofHom` and coproduct injections.
  This localizes failure later than `t0`-`t3`.

#### `medium/medium_leancat_008_t5`

| Seq range | Role | Purpose | Action and evidence | Interpretation |
|---|---|---|---|---|
| 1..79 | Reasoner/engineer/critic | inclusions | 20 checks; candidate accepted after two failed submissions | Productive local repair |
| 80..103 | Engineer/critic | universal map | First candidate compiles but critic rejects it as only a helper | Critic checks semantic scope, not just compilation |
| 104..133 | Engineer/critic | universal property | Revised helper reviewed and accepted even though critic feedback says it does not fully prove the property | Subgoal-level false acceptance |
| 134..157 | Engineer/critic | isomorphism | Candidate contains `sorry`; critic rejects | False progress blocked |
| 158..201 | Engineer/reasoner | integration retries | Ten searches, six failed checks, two late revisions; `cap` | No complete inverse proof |

- **Counts:** 28 searches; probes 18/8; subgoals 4/16; reviews 4/0.
- **Final plan:** the ledger marks inclusion and universal-property nodes
  accepted; mathematical audit accepts only the inclusion node. The isomorphism
  node is active after ten attempts; final wrapper pending.
- **Communication:** `R->E=1`, `E->R=1`, `C->E=4`.
- **Critical failure:** the critic first correctly rejects a lift-only helper,
  then accepts another helper while explicitly saying it “doesn't fully prove
  the universal property.” The plan advances on an undischarged dependency.
  The checked reference proof shows the node was completable with
  `Monoid.Coprod.lift_unique`; the run simply did not prove it.

#### `medium/medium_leancat_008_t6`

| Seq range | Role | Purpose | Action and evidence | Interpretation |
|---|---|---|---|---|
| 1..35 | Reasoner/engineer/critic | group-instance node | Tiny artifact submitted and accepted | Formally valid but mathematically low-value milestone |
| 36..110 | Engineer | first morphism | 20 searches, 15 checks, eight failures; return to reasoner | Typeclass/coercion diagnosis blocks construction |
| 111..199 | Reasoner/engineer | retrieval stall | Two plan revisions but 43 searches and no further compile evidence | Strategy update is not executed |
| 200..201 | System | termination | `cap` | Three substantive nodes remain unfinished |

- **Counts:** 68 searches; probes 8/5; subgoals 1/3; reviews 1/0.
- **Final plan:** group-structure node accepted; first morphism active after three
  failed candidates; two later nodes pending.
- **Communication:** `R->E=1`, `E->R=1`, `C->E=1`.
- **Critical failure:** the initial node proves little beyond an existing
  instance. After morphism failures, retrieval consumes the remaining budget.
  This is a plan-quality failure followed by search perseveration.

#### `medium/medium_leancat_008_t7`

| Seq range | Role | Purpose | Action and evidence | Interpretation |
|---|---|---|---|---|
| 1..111 | Reasoner/engineer/critic | first morphism | 28 checks; first submission rejected for `sorry`, repaired candidate accepted | Strong critic-assisted repair |
| 112..131 | Engineer/critic | reverse morphism | Map definitions are accepted, but both submitted theorem bodies retain later `sorry` | Local definitions valid; whole artifacts are not sorry-free |
| 132..141 | Engineer/critic | first identity | `sorry` candidate compiles; critic rejects | Gate correctly blocks incomplete proof |
| 142..150 | Engineer/system | attempted repair | Two searches; final check has malformed JSON arguments; `stuck` | No reasoner reentry after rejection |

- **Counts:** 20 searches; probes 17/7; subgoals 4/3; reviews 4/0.
- **Final plan:** two map nodes are accepted and their definitions are
  mathematically valid, but the submitted files are contaminated by later
  `sorry`; first identity active, second identity and iso pending.
- **Communication:** `R->E=1`, `E->R=0`, `C->E=4`.
- **Critical failure:** the critic correctly rejects the identity proof, but it
  permits scoped acceptance of map definitions embedded in non-sorry-free
  theorem bodies. The run then returns only to local engineering and stops
  before a strategy-level response.

#### `medium/medium_leancat_008_t8`

| Seq range | Role | Purpose | Action and evidence | Interpretation |
|---|---|---|---|---|
| 1..53 | Reasoner/engineer/critic | inclusions | 12 checks; candidate reviewed and accepted | First node verified |
| 54..83 | Engineer | map to categorical coproduct | Ten checks, six failures | Typeclass/coercion failures dominate |
| 84..110 | Engineer/reasoner | diagnosis loop | Two engineer returns, one revision, several self-routes | Model repeatedly attributes failure to missing theorem context |
| 111..115 | Reasoner/system | stalled response | Long repeated narrative; `stuck` at 114 turns | No executable next action selected |

- **Counts:** 17 searches; probes 12/6; subgoals 1/4; reviews 1/0.
- **Final plan:** inclusions accepted; first map active after four submitted
  attempts; reverse map and inverse proof pending.
- **Communication:** `R->E=1`, `E->R=2`, `C->E=1`, plus one implicit reasoner
  reentry.
- **Critical failure:** the trace records `canonical_prelude_applied=true`, so
  the repeated claim that the tool simply omitted `[HasBinaryCoproduct G H]` is
  not established by the evidence. Diagnosis repetition replaces a concrete
  coercion/API experiment.

#### `medium/medium_leancat_008_t9`

| Seq range | Role | Purpose | Action and evidence | Interpretation |
|---|---|---|---|---|
| 1..75 | Reasoner/engineer/critic | group-instance node | 11 checks and 13 searches; weak first node accepted | Valid artifact, little movement toward the theorem |
| 76..99 | Engineer/reasoner | isomorphism planning | Several self-routes and two reasoner-to-engineer routes | Recognizes universal properties but does not form a candidate |
| 100..199 | Engineer | retrieval perseveration | 49 searches, no compiler call or submission | Search volume becomes detached from proof state |
| 200..201 | System | termination | `cap` | Universal-property node has zero attempts |

- **Counts:** 74 searches; probes 8/1; subgoals 1/1; reviews 1/0.
- **Final plan:** group-instance node accepted; direct-isomorphism node active
  with zero submitted attempts; two nodes pending.
- **Communication:** `R->E=2`, `E->R=0`, `C->E=1`; other routes are self-routes.
- **Critical failure:** the decomposition starts with a low-information node and
  never turns the central universal-property idea into Lean. This is the
  clearest medium example of retrieval perseveration.

#### Medium Cohort Verdict

The stable O1 boundary is broader than “inclusions fail.” All ten verify one
preliminary artifact. The ledger marks two in `t4`, `t5`, and `t7`, but only
`t4` has two clean, fully scoped artifacts; `t5` advances an incomplete
universal-property node and `t7` scopes valid map definitions out of theorem
bodies that still contain `sorry`. The unrecovered boundary is one of:

- proving the free product's universal property (`t0`-`t3`);
- proving inverse equations after constructing both maps (`t4`, `t7`);
- advancing past a falsely accepted incomplete universal artifact (`t5`);
- or failing to make the plan substantive/executable (`t6`, `t8`, `t9`).

This supports a task-specific failure taxonomy. It does not establish O1/O2
precision or O3 prediction, because there is one medium theorem, one backbone,
one setup, and no independent event-level gold labels.

## 5. Passed Easy Behavior Matrix

The 56 canonical rows below are independently accepted in the existing
reviewed analysis. The six recovery rows are compact because their historical
summaries say `solved`, but the fresh strict audit was infrastructure-unknown;
their kernel cell therefore says **historical**, not freshly confirmed.

`R-E/E-R/E-C/C-E` gives the four directional handoff counts.

| Trace key | Strategy | Search/check | Compile ok/fail | Recovered incidents | Critic | Route | Kernel evidence |
|---|---|---:|---:|---:|---|---|---|
| `canonical/easy_fatem_011_t0` | valid | 1/1 | 1/0 | 0 | approval, no recheck | 1/0/1/0 | accepted |
| `canonical/easy_fatem_011_t1` | valid | 1/2 | 2/0 | 0 | compile checked | 1/0/1/0 | accepted |
| `canonical/easy_fatem_011_t2` | valid | 1/1 | 1/0 | 0 | approval, no recheck | 1/0/1/0 | accepted |
| `canonical/easy_fatem_011_t3` | valid | 1/2 | 2/0 | 0 | compile checked | 1/0/1/0 | accepted |
| `canonical/easy_fatem_011_t4` | valid | 1/1 | 1/0 | 0 | approval, no recheck | 1/0/1/0 | accepted |
| `canonical/easy_fatem_011_t5` | valid | 1/1 | 1/0 | 0 | approval, no recheck | 1/0/1/0 | accepted |
| `canonical/easy_fatem_011_t6` | valid | 1/1 | 1/0 | 0 | approval, no recheck | 1/0/1/0 | accepted |
| `canonical/easy_fatem_011_t7` | valid | 1/1 | 1/0 | 0 | approval, no recheck | 1/0/1/0 | accepted |
| `canonical/easy_fatem_011_t8` | valid | 1/1 | 1/0 | 0 | approval, no recheck | 1/0/1/0 | accepted |
| `canonical/easy_fatem_011_t9` | valid | 1/1 | 1/0 | 0 | approval, no recheck | 1/0/1/0 | accepted |
| `canonical/easy_fatem_012_t0` | partial | 2/5 | 2/3 | 3 | compile checked | 1/0/1/0 | accepted |
| `canonical/easy_fatem_012_t1` | valid | 2/6 | 4/2 | 2 | approval, no recheck | 1/0/1/0 | accepted |
| `canonical/easy_fatem_012_t2` | partial | 1/4 | 2/2 | 2 | approval, no recheck | 1/0/1/0 | accepted |
| `canonical/easy_fatem_012_t3` | valid | 2/6 | 3/3 | 3 | compile checked | 1/0/1/0 | accepted |
| `canonical/easy_fatem_012_t4` | partial | 3/3 | 1/2 | 2 | approval, no recheck | 1/0/1/0 | accepted |
| `canonical/easy_fatem_012_t5` | partial | 2/9 | 4/5 | 5 | approval, no recheck | 1/0/1/0 | accepted |
| `canonical/easy_fatem_012_t6` | valid | 2/2 | 2/0 | 0 | compile checked | 1/0/1/0 | accepted |
| `canonical/easy_fatem_012_t7` | valid | 2/3 | 2/1 | 1 | compile checked | 1/0/1/0 | accepted |
| `canonical/easy_fatem_012_t8` | partial | 2/3 | 2/1 | 1 | compile checked | 1/0/1/0 | accepted |
| `canonical/easy_fatem_012_t9` | partial | 1/2 | 1/1 | 1 | approval, no recheck | 1/0/1/0 | accepted |
| `canonical/easy_fatem_020_t0` | valid | 3/3 | 1/2 | 2 | approval, no recheck | 1/0/1/0 | accepted |
| `canonical/easy_fatem_020_t1` | valid | 2/4 | 2/2 | 2 | compile checked | 1/0/1/0 | accepted |
| `canonical/easy_fatem_020_t6` | valid | 1/1 | 1/0 | 0 | approval, no recheck | 1/0/1/0 | accepted |
| `canonical/easy_fatem_041_t0` | valid | 1/1 | 1/0 | 0 | approval, no recheck | 1/0/1/0 | accepted |
| `canonical/easy_fatem_041_t1` | valid | 1/1 | 1/0 | 0 | approval, no recheck | 1/0/1/0 | accepted |
| `canonical/easy_fatem_041_t2` | valid | 1/1 | 1/0 | 0 | approval, no recheck | 1/0/1/0 | accepted |
| `canonical/easy_fatem_041_t3` | valid | 2/1 | 1/0 | 0 | approval, no recheck | 1/0/1/0 | accepted |
| `canonical/easy_fatem_041_t4` | valid | 1/1 | 1/0 | 0 | approval, no recheck | 1/0/1/0 | accepted |
| `canonical/easy_fatem_041_t5` | valid | 1/1 | 1/0 | 0 | approval, no recheck | 1/0/1/0 | accepted |
| `canonical/easy_fatem_041_t6` | valid | 1/1 | 1/0 | 0 | approval, no recheck | 1/0/1/0 | accepted |
| `canonical/easy_fatem_041_t7` | valid | 1/1 | 1/0 | 0 | approval, no recheck | 1/0/1/0 | accepted |
| `canonical/easy_fatem_041_t8` | valid | 1/1 | 1/0 | 0 | approval, no recheck | 1/0/1/0 | accepted |
| `canonical/easy_fatem_041_t9` | valid | 1/2 | 2/0 | 0 | compile checked | 1/0/1/0 | accepted |
| `canonical/easy_fatem_109_t0` | valid | 1/2 | 2/0 | 0 | compile checked | 1/0/1/0 | accepted |
| `canonical/easy_fatem_109_t1` | valid | 2/2 | 2/0 | 0 | compile checked | 1/0/1/0 | accepted |
| `canonical/easy_fatem_109_t2` | valid | 2/1 | 1/0 | 0 | approval, no recheck | 1/0/1/0 | accepted |
| `canonical/easy_fatem_109_t4` | valid | 2/1 | 1/0 | 0 | approval, no recheck | 1/0/1/0 | accepted |
| `canonical/easy_fatem_109_t5` | valid | 2/1 | 1/0 | 0 | approval, no recheck | 1/0/1/0 | accepted |
| `canonical/easy_fatem_109_t6` | valid | 2/2 | 2/0 | 0 | compile checked | 1/0/1/0 | accepted |
| `canonical/easy_fatem_109_t7` | valid | 2/2 | 2/0 | 0 | compile checked | 1/0/1/0 | accepted |
| `canonical/easy_fatem_109_t8` | valid | 7/2 | 2/0 | 0 | compile checked | 1/0/1/0 | accepted |
| `canonical/easy_leancat_001_t1` | valid | 5/9 | 2/7 | 7 | critic missing | 1/0/0/0 | accepted target, review incomplete |
| `canonical/easy_leancat_001_t2` | partial | 1/1 | 1/0 | 0 | approval, no recheck | 1/0/1/0 | accepted |
| `canonical/easy_leancat_001_t4` | partial | 3/2 | 2/0 | 0 | compile checked | 1/0/1/0 | accepted |
| `canonical/easy_leancat_001_t7` | partial | 4/4 | 3/1 | 1 | approval, no recheck | 1/0/1/0 | accepted |
| `canonical/easy_leancat_001_t8` | partial | 2/2 | 2/0 | 0 | compile checked | 1/0/1/0 | accepted |
| `canonical/easy_leancat_001_t9` | valid | 2/8 | 3/5 | 5 | compile checked | 1/0/1/0 | accepted |
| `canonical/easy_leancat_002_t0` | partial | 3/2 | 2/0 | 0 | compile checked | 1/0/1/0 | accepted |
| `canonical/easy_leancat_002_t2` | partial | 3/2 | 2/0 | 0 | compile checked | 1/0/1/0 | accepted |
| `canonical/easy_leancat_002_t3` | partial | 2/2 | 2/0 | 0 | compile checked | 1/0/1/0 | accepted |
| `canonical/easy_leancat_002_t4` | partial | 1/3 | 1/2 | 2 | approval, no recheck | 1/0/1/0 | accepted |
| `canonical/easy_leancat_002_t5` | partial | 2/2 | 2/0 | 0 | compile checked | 1/0/1/0 | accepted |
| `canonical/easy_leancat_002_t6` | partial | 2/2 | 2/0 | 0 | compile checked | 1/0/1/0 | accepted |
| `canonical/easy_leancat_002_t7` | partial | 2/3 | 2/1 | 1 | compile checked | 1/0/1/0 | accepted |
| `canonical/easy_leancat_002_t8` | partial | 3/2 | 2/0 | 0 | compile checked | 1/0/1/0 | accepted |
| `canonical/easy_leancat_002_t9` | partial | 3/3 | 2/1 | 1 | compile checked | 1/0/1/0 | accepted |
| `recovery/easy_fatem_011_t0` | task-aligned | 2/1 | 1/0 | not reviewed | approval, no recheck | 1/0/1/0 | historical offline accepted |
| `recovery/easy_fatem_020_t0` | task-aligned | 3/3 | 2/1 | not reviewed | compile checked | 1/0/1/0 | historical offline accepted |
| `recovery/easy_fatem_041_t0` | task-aligned | 1/1 | 1/0 | not reviewed | approval, no recheck | 1/0/1/0 | historical offline accepted |
| `recovery/easy_fatem_111_t0` | task-aligned | 3/5 | 2/3 | not reviewed | compile checked | 1/0/1/0 | historical offline accepted |
| `recovery/easy_leancat_001_t0` | task-aligned | 2/1 | 1/0 | not reviewed | approval, no recheck | 1/0/1/0 | historical offline accepted |
| `recovery/easy_leancat_002_t0` | task-aligned | 2/1 | 1/0 | not reviewed | approval, no recheck | 1/0/1/0 | historical offline accepted |

### What The Passed Runs Teach

- Direct library matches (`mul_sub`, `sub_mul`, `Prod.orderOf_mk`, mono
  instances) yield short, stable paths.
- A passed run can contain many failures: FATEM012 `t5` recovers five incidents;
  LeanCat001 `t1` and `t9` recover seven and five. Failed checks measure search
  cost, not final incorrectness.
- Thirty of the 56 canonical passed traces use critic approval without a
  fresh critic compile. Kernel acceptance makes their final artifact trustworthy
  in this dataset, but the critic behavior itself remains shallow.
- Canonical LeanCat001 `t1` has an accepted exact target but no completed critic
  handoff. It is proof-valid and workflow-incomplete, which are different axes.

## 6. Cross-Trace Findings

### 6.1 Corpus-Level Process Counts

| Cohort | Traces | Events | Searches | Lean checks | Compile ok/fail | Critic rechecks | Approvals/rejections | Chain/non-chain |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Canonical easy | 100 | 1,726 | 362 | 341 | 123/218 | 30 | 59/0 | 97/3 |
| Recovery prompt | 10 | 168 | 35 | 32 | 18/14 | 3 | 8/0 | 10/0 |
| Tool-routed easy | 3 | 179 | 8 | 29 | 14/15 | 6 | 1/1 | 3/0 |
| Interrupted audit | 1 | 47 | 2 | 7 | 2/5 | 1 | 0/0 | 1/0 |
| Medium subgoals | 10 | 1,828 | 342 | 395 | 204/188 | 19 | 0/6 | 3/7 |
| **Total** | **124** | **3,948** | **749** | **804** | **361/440** | **59** | **68/7** | **114/10** |

Medium `t1` ends with one unresolved check. The final calls in `t2` and `t7`
receive execution results, but those results report unterminated JSON arguments
rather than Lean compiler verdicts. Thus 804 calls yield 801 verdicts. These
three observations are neither implicit failures nor successes of the proof.

### 6.2 Reasoner Behavior

The reasoner has three recurring modes:

1. **Short exact-library plan.** FATEM011, FATEM041, FATEM109, and LeanCat002
   often need one known lemma or instance. These routes usually solve quickly.
2. **Mathematically valid but API-incomplete plan.** FATEM019, FATEM020,
   FATEM111, LeanCat001, and medium LeanCat008 show that knowing a paper proof
   does not specify coercions, instances, theorem orientation, or tactic-state
   transitions.
3. **Retrieval without commitment.** FATEM019 `t5/t7`, FATEM020 `t3`, FATEM109
   `t3/t9`, LeanCat002 `t1`, and recovery FATEM019 never produce an actionable
   handoff. The current perseveration detector undercounts this because query
   text changes while the mathematical state stays fixed.

The medium reasoners generally decompose the theorem sensibly. Their weakness
is converting a revised mathematical description into a new Lean invariant.
Across ten trials there are 12 recorded strategy revisions and ten explicit
engineer-to-reasoner returns, but no verified completion. `t3` communicates
frequently without escaping the same uniqueness obligation; `t6` and `t9`
revise or discuss strategy and then spend most of the remaining budget on
retrieval.

### 6.3 Engineer Behavior

Canonical reviewed symptoms are multi-label and include recovered incidents:

| Symptom | Traces containing it |
|---|---:|
| `opaque_compiler_failure` | 23 |
| `application_type_mismatch` | 21 |
| `tactic_failure` | 14 |
| `type_mismatch` | 12 |
| `unknown_symbol` | 11 |
| `typeclass_resolution` | 11 |
| `target_not_attempted` | 6 |
| `statement_drift` | 5 |
| `invalid_import_path` | 2 |
| `sorry_pseudo_pass` | 1 |
| `critic_approval_after_failed_recheck` | 1 |
| `target_unreviewed` | 1 |

The dominant bounded causal labels are `lean_type_failure` (36 traces),
`tooling_diagnostic_unknown` (23), `lean_elaboration_failure` (15),
`lean_tactic_failure` (14), and `api_or_library_hallucination` (13).

Three engineer-level distinctions matter:

- **Local repair can be productive.** FATEM012 often fails several times and
  then reaches a clean exact proof. Retry count alone is not pathology.
- **Successful helpers can mask non-progress.** FATEM020 `t8`, FATEM111 `t0`,
  LeanCat001 `t0/t6`, and the medium runs compile fragments without closing the
  target or active subgoal.
- **Changing the environment can fake progress.** FATEM115's local
  `Transitive` definition and `IsTrans` substitutions make later checks easier
  by changing what is being checked.

### 6.4 Critic Behavior

The critic acts more like a terminal judge than a collaborator in the original
architecture:

- canonical: 59 engineer-to-critic handoffs, zero critic-to-engineer returns;
- recovery: eight engineer-to-critic handoffs, zero returns;
- tool-routed: five engineer-to-critic and three critic-to-engineer routes;
- medium: no engineer-initiated critic route, but 19 critic-to-engineer tool
  routes after automatic subgoal submission.

Compilation by the critic is stronger than narrative approval, but still only
checks the supplied candidate. FATEM115 demonstrates two separate failures:

1. **False acceptance:** the critic accepts an independently rejected changed
   statement (`t2`, `t4`, `t5`, `t8`).
2. **Critic masking:** in `t2`, the critic's own later relevant recheck fails and
   it still approves. Only this narrower trace has the trace-internal
   contradiction required by the guide's `critic_masking` label.

The tool-routed critic is behaviorally stricter: it rejects one run, returns to
the engineer, and requires subgoal evidence hashes. Yet `t2` still completes a
changed contract. A gate is only as faithful as the artifact definition it
checks.

The medium mathematical audit adds two subgoal-gate failures:

- `t5` is a **subgoal-level false accept**: the critic says the candidate does
  not fully prove the universal property, then accepts that node anyway.
- `t7` uses **scope leakage**: the map definitions are valid, but the reviewed
  theorem bodies contain later `sorry`; acceptance depends on ignoring part of
  the submitted artifact.

Neither is a false final-theorem approval, because no medium run completes.

### 6.5 Communication And Global Coordination

| Direction | Count across 124 |
|---|---:|
| Reasoner -> engineer | 127 |
| Engineer -> reasoner | 11 |
| Engineer -> critic | 73 |
| Critic -> engineer | 22 |

These counts support four conclusions:

- The original runs are delegation pipelines, not deliberative teams.
- Prompt-only freedom does not create return communication.
- Typed routing creates more interaction, but not parallel execution. Seven of
  ten medium graphs are non-chain only because recorded causal parentage
  branches around routes and controller events.
- More communication is not itself improvement. Productive communication must
  carry compiler evidence and change the next mathematical action.

### 6.6 Probe Success Is Not Proof Progress

The medium cohort makes the distinction measurable:

| Purpose | Successful | Failed | Interpretation |
|---|---:|---:|---|
| Probe | 166 | 116 | Names, signatures, expressions, or partial constructions |
| Subgoal | 19 | 72 | Candidate artifacts for ledger nodes |
| Critic review | 19 | 0 | Rechecks of submitted subgoal candidates |

The 19 compiling candidates all reach a compiling critic recheck: the workflow
accepts 13 and rejects six. Compilation is still weaker than subgoal discharge:
`t5` node 2 is accepted despite critic text admitting it does not fully prove
the universal property, and `t7` accepts local map definitions from larger
theorem bodies containing `sorry`. `t1` reports 44 successful compiler results,
but 42 are probes, one is the candidate, and one is its review. Presenting “44
successful compiles” without purpose would invert the meaning of the run.

### 6.7 Four Task Comparisons

#### FATEM019: Stable API Bridge Failure

- Canonical result: 0/10 solved.
- Recovery result: reasoner-only 14-search stall.
- Math: standard and plausible.
- Failure: unstable theorem names and proposition/typeclass conversions.
- Agent lesson: the reasoner must hand off an exact API contract, not only a
  paper theorem.

#### FATEM111: Formalization Failure Despite A Valid Strategy

- Canonical result: 0/10 solved.
- Recovery historical result: one solved label after three failed and two
  successful checks.
- Math: every canonical reasoner gives the right expansion.
- Failure: `Commute` exposure, noncommutative normalization, and rewriting
  `pow_two`; many diagnostics are opaque.
- Agent lesson: a valid strategy label is too coarse to predict execution.

#### FATEM115: Fidelity And Critic Failure

- Canonical result: six unsolved, four silent failures.
- Tool-routed result: two unsolved, one runtime-complete silent failure.
- Math: short direct proof.
- Failure: implicit arguments initially; statement replacement later.
- Agent lesson: independent exact-header checking must be outside the same
  mutable candidate environment.

#### Medium LeanCat008: Localized Universal-Property Bottleneck

- All ten trials accept at least one preliminary node; the ledger reports two
  accepted nodes for `t4`, `t5`, and `t7`.
- Mathematical audit confirms both clean directional-map artifacts only in
  `t4`. `t5`'s second accepted artifact does not prove its declared universal
  property, while `t7`'s valid map definitions sit inside theorem bodies that
  still contain `sorry`.
- Both the cofan and direct-map strategies are nevertheless formally
  completable; independent reference proofs pass the pinned Lean compiler.
- Seven terminate at the 200-turn cap; `t2`, `t7`, and `t8` terminate as
  `stuck` after 145, 149, and 114 turns.
- No trial submits an independently verified exact target or records
  `run_complete=true`.
- Agent lesson: decomposition exposes where progress stops, but the controller
  needs a policy for converting prolonged probe exploration into a reasoner
  revision or bounded stop.

### 6.8 Task Difficulty, Architecture Failure, And Infrastructure

These must remain separate:

- **Task/API difficulty:** FATEM019 and medium LeanCat008 repeatedly fail at the
  same mathematical-library bridge across trials.
- **Architecture failure:** missing return routes, critic terminality, and
  search/probe stalls recur across unrelated tasks.
- **Agent coding failure:** hallucinated names/imports, argument mismatch,
  typeclass confusion, and tactic misuse are visible in compiler evidence.
- **Infrastructure uncertainty:** opaque historical compiler responses and the
  earlier strict rescore that produced no verdict. These are `unknown`, never
  silently counted as model errors.

### 6.9 Proposal Interpretation

**Supported now:**

- event- and role-level localization of observed compiler, routing, statement,
  and critic failures;
- an exploratory multi-level taxonomy;
- concrete examples of output/trajectory disagreement and critic masking;
- a clear medium subgoal boundary where progress stops.

**Not supported now:**

- O1 localization precision/recall, because raw automatic anchor labels are
  absent;
- O2 detector precision/recall, because reviewed labels are not an independent
  expert gold set;
- O3 early prediction, because there is no matched stress progression;
- claims that more agent interaction improves correctness;
- claims that graph structure explains model-level causes.

The presentation-safe conclusion is:

> Lean's kernel and typed tool evidence make hidden workflow failures visible,
> but only when probe, subgoal, critic, and exact-target evidence are kept
> separate. In this corpus, mathematically plausible planning often fails at
> the Lean API boundary, and additional communication does not prevent silent
> failure when every role checks the same altered statement.

## 7. Complete Trace Index And Reproducibility

Every source JSONL in the pre-consolidation snapshot appears exactly once below.
`none` in the terminal column means the historical trace has no explicit
terminal event; it does not mean the process was observed running. Hashes are
frozen pre-consolidation SHA-256 prefixes; approved public path-token
sanitization can therefore change a current file hash without changing the
scientific fields interpreted here. The full combined hash at the start of the
report commits to the pre-consolidation per-file hashes and paths. Relocated V1
and medium paths below show the current public layout; external-only historical
sources retain their pre-consolidation path notation.

| Trace key | Depth | Outcome label | Events | Terminal | SHA-256 prefix | Source |
|---|---|---|---:|---|---|---|
| `canonical/easy_fatem_011_t0` | compact | solved | 8 | none | `95a7b2665f20` | `data/batch/version_1_trial_traces/easy_fatem_011_t0.jsonl` |
| `canonical/easy_fatem_011_t1` | compact | solved | 10 | none | `c5708c696f86` | `data/batch/version_1_trial_traces/easy_fatem_011_t1.jsonl` |
| `canonical/easy_fatem_011_t2` | compact | solved | 8 | none | `1fd748ee8d30` | `data/batch/version_1_trial_traces/easy_fatem_011_t2.jsonl` |
| `canonical/easy_fatem_011_t3` | compact | solved | 10 | none | `28b543c6df31` | `data/batch/version_1_trial_traces/easy_fatem_011_t3.jsonl` |
| `canonical/easy_fatem_011_t4` | compact | solved | 8 | none | `d268d927fe3c` | `data/batch/version_1_trial_traces/easy_fatem_011_t4.jsonl` |
| `canonical/easy_fatem_011_t5` | compact | solved | 8 | none | `41a0c9dfc604` | `data/batch/version_1_trial_traces/easy_fatem_011_t5.jsonl` |
| `canonical/easy_fatem_011_t6` | compact | solved | 8 | none | `7df0fe14085f` | `data/batch/version_1_trial_traces/easy_fatem_011_t6.jsonl` |
| `canonical/easy_fatem_011_t7` | compact | solved | 8 | none | `4f1efdfecd29` | `data/batch/version_1_trial_traces/easy_fatem_011_t7.jsonl` |
| `canonical/easy_fatem_011_t8` | compact | solved | 8 | none | `032412808a92` | `data/batch/version_1_trial_traces/easy_fatem_011_t8.jsonl` |
| `canonical/easy_fatem_011_t9` | compact | solved | 8 | none | `2ffbf5e9dc11` | `data/batch/version_1_trial_traces/easy_fatem_011_t9.jsonl` |
| `canonical/easy_fatem_012_t0` | compact | solved | 18 | none | `80e8683f57be` | `data/batch/version_1_trial_traces/easy_fatem_012_t0.jsonl` |
| `canonical/easy_fatem_012_t1` | compact | solved | 20 | none | `f01157b8eaf0` | `data/batch/version_1_trial_traces/easy_fatem_012_t1.jsonl` |
| `canonical/easy_fatem_012_t2` | compact | solved | 14 | none | `2f6d0e6e56a0` | `data/batch/version_1_trial_traces/easy_fatem_012_t2.jsonl` |
| `canonical/easy_fatem_012_t3` | compact | solved | 20 | none | `a7030d9a5229` | `data/batch/version_1_trial_traces/easy_fatem_012_t3.jsonl` |
| `canonical/easy_fatem_012_t4` | compact | solved | 16 | none | `a3e19517eac6` | `data/batch/version_1_trial_traces/easy_fatem_012_t4.jsonl` |
| `canonical/easy_fatem_012_t5` | compact | solved | 26 | none | `0121f84d1ada` | `data/batch/version_1_trial_traces/easy_fatem_012_t5.jsonl` |
| `canonical/easy_fatem_012_t6` | compact | solved | 12 | none | `5733e3e8ff27` | `data/batch/version_1_trial_traces/easy_fatem_012_t6.jsonl` |
| `canonical/easy_fatem_012_t7` | compact | solved | 14 | none | `30a28c962554` | `data/batch/version_1_trial_traces/easy_fatem_012_t7.jsonl` |
| `canonical/easy_fatem_012_t8` | compact | solved | 14 | none | `f7e0349c07df` | `data/batch/version_1_trial_traces/easy_fatem_012_t8.jsonl` |
| `canonical/easy_fatem_012_t9` | compact | solved | 10 | none | `b97aa8accb4b` | `data/batch/version_1_trial_traces/easy_fatem_012_t9.jsonl` |
| `canonical/easy_fatem_019_t0` | deep | unsolved | 30 | none | `260f6a55ff6d` | `data/batch/version_1_trial_traces/easy_fatem_019_t0.jsonl` |
| `canonical/easy_fatem_019_t1` | deep | unsolved | 30 | none | `484b94169e7b` | `data/batch/version_1_trial_traces/easy_fatem_019_t1.jsonl` |
| `canonical/easy_fatem_019_t2` | deep | unsolved | 30 | none | `7384d05fc75f` | `data/batch/version_1_trial_traces/easy_fatem_019_t2.jsonl` |
| `canonical/easy_fatem_019_t3` | deep | unsolved | 30 | none | `f2de267c74fb` | `data/batch/version_1_trial_traces/easy_fatem_019_t3.jsonl` |
| `canonical/easy_fatem_019_t4` | deep | unsolved | 30 | none | `17f134526da2` | `data/batch/version_1_trial_traces/easy_fatem_019_t4.jsonl` |
| `canonical/easy_fatem_019_t5` | deep | unsolved | 26 | none | `c3c14097a633` | `data/batch/version_1_trial_traces/easy_fatem_019_t5.jsonl` |
| `canonical/easy_fatem_019_t6` | deep | unsolved | 30 | none | `e1dda368def5` | `data/batch/version_1_trial_traces/easy_fatem_019_t6.jsonl` |
| `canonical/easy_fatem_019_t7` | deep | unsolved | 16 | none | `fcb88e27ef28` | `data/batch/version_1_trial_traces/easy_fatem_019_t7.jsonl` |
| `canonical/easy_fatem_019_t8` | deep | unsolved | 30 | none | `e0c14ba8c918` | `data/batch/version_1_trial_traces/easy_fatem_019_t8.jsonl` |
| `canonical/easy_fatem_019_t9` | deep | unsolved | 30 | none | `17903e4e85e8` | `data/batch/version_1_trial_traces/easy_fatem_019_t9.jsonl` |
| `canonical/easy_fatem_020_t0` | compact | solved | 16 | none | `f663509439ce` | `data/batch/version_1_trial_traces/easy_fatem_020_t0.jsonl` |
| `canonical/easy_fatem_020_t1` | compact | solved | 16 | none | `c80a698e47e8` | `data/batch/version_1_trial_traces/easy_fatem_020_t1.jsonl` |
| `canonical/easy_fatem_020_t2` | deep | unsolved | 18 | none | `39c39066233d` | `data/batch/version_1_trial_traces/easy_fatem_020_t2.jsonl` |
| `canonical/easy_fatem_020_t3` | deep | unsolved | 12 | none | `2d8fe59406cb` | `data/batch/version_1_trial_traces/easy_fatem_020_t3.jsonl` |
| `canonical/easy_fatem_020_t4` | deep | unsolved | 30 | none | `9dfc9cfdc441` | `data/batch/version_1_trial_traces/easy_fatem_020_t4.jsonl` |
| `canonical/easy_fatem_020_t5` | deep | unsolved | 16 | none | `bd5e50447ccb` | `data/batch/version_1_trial_traces/easy_fatem_020_t5.jsonl` |
| `canonical/easy_fatem_020_t6` | compact | solved | 8 | none | `60c3452e7e83` | `data/batch/version_1_trial_traces/easy_fatem_020_t6.jsonl` |
| `canonical/easy_fatem_020_t7` | deep | unsolved | 18 | none | `15dbf6d04026` | `data/batch/version_1_trial_traces/easy_fatem_020_t7.jsonl` |
| `canonical/easy_fatem_020_t8` | deep | unsolved | 30 | none | `f837f20dcc5b` | `data/batch/version_1_trial_traces/easy_fatem_020_t8.jsonl` |
| `canonical/easy_fatem_020_t9` | deep | unsolved | 18 | none | `05f20de31c41` | `data/batch/version_1_trial_traces/easy_fatem_020_t9.jsonl` |
| `canonical/easy_fatem_041_t0` | compact | solved | 8 | none | `96e82f022d82` | `data/batch/version_1_trial_traces/easy_fatem_041_t0.jsonl` |
| `canonical/easy_fatem_041_t1` | compact | solved | 8 | none | `a90430573fc2` | `data/batch/version_1_trial_traces/easy_fatem_041_t1.jsonl` |
| `canonical/easy_fatem_041_t2` | compact | solved | 8 | none | `b8330fee0095` | `data/batch/version_1_trial_traces/easy_fatem_041_t2.jsonl` |
| `canonical/easy_fatem_041_t3` | compact | solved | 10 | none | `52c05d603dee` | `data/batch/version_1_trial_traces/easy_fatem_041_t3.jsonl` |
| `canonical/easy_fatem_041_t4` | compact | solved | 8 | none | `ff9b06f1e95e` | `data/batch/version_1_trial_traces/easy_fatem_041_t4.jsonl` |
| `canonical/easy_fatem_041_t5` | compact | solved | 8 | none | `a9d998284c14` | `data/batch/version_1_trial_traces/easy_fatem_041_t5.jsonl` |
| `canonical/easy_fatem_041_t6` | compact | solved | 8 | none | `f076295aa9f3` | `data/batch/version_1_trial_traces/easy_fatem_041_t6.jsonl` |
| `canonical/easy_fatem_041_t7` | compact | solved | 8 | none | `9b1e73195773` | `data/batch/version_1_trial_traces/easy_fatem_041_t7.jsonl` |
| `canonical/easy_fatem_041_t8` | compact | solved | 8 | none | `9b13d289fda4` | `data/batch/version_1_trial_traces/easy_fatem_041_t8.jsonl` |
| `canonical/easy_fatem_041_t9` | compact | solved | 10 | none | `917158a33d29` | `data/batch/version_1_trial_traces/easy_fatem_041_t9.jsonl` |
| `canonical/easy_fatem_109_t0` | compact | solved | 10 | none | `7df5215495ed` | `data/batch/version_1_trial_traces/easy_fatem_109_t0.jsonl` |
| `canonical/easy_fatem_109_t1` | compact | solved | 12 | none | `5c08b558b97e` | `data/batch/version_1_trial_traces/easy_fatem_109_t1.jsonl` |
| `canonical/easy_fatem_109_t2` | compact | solved | 10 | none | `899a69a6b75d` | `data/batch/version_1_trial_traces/easy_fatem_109_t2.jsonl` |
| `canonical/easy_fatem_109_t3` | deep | unsolved | 24 | none | `70adfa21bedb` | `data/batch/version_1_trial_traces/easy_fatem_109_t3.jsonl` |
| `canonical/easy_fatem_109_t4` | compact | solved | 10 | none | `4a933e4d7337` | `data/batch/version_1_trial_traces/easy_fatem_109_t4.jsonl` |
| `canonical/easy_fatem_109_t5` | compact | solved | 10 | none | `35e6a6cc43e0` | `data/batch/version_1_trial_traces/easy_fatem_109_t5.jsonl` |
| `canonical/easy_fatem_109_t6` | compact | solved | 12 | none | `5a12f966b123` | `data/batch/version_1_trial_traces/easy_fatem_109_t6.jsonl` |
| `canonical/easy_fatem_109_t7` | compact | solved | 12 | none | `fd7437d1ec41` | `data/batch/version_1_trial_traces/easy_fatem_109_t7.jsonl` |
| `canonical/easy_fatem_109_t8` | compact | solved | 22 | none | `cec8d6e9f054` | `data/batch/version_1_trial_traces/easy_fatem_109_t8.jsonl` |
| `canonical/easy_fatem_109_t9` | deep | unsolved | 6 | none | `035abf684182` | `data/batch/version_1_trial_traces/easy_fatem_109_t9.jsonl` |
| `canonical/easy_fatem_111_t0` | deep | unsolved | 30 | none | `876b333bf277` | `data/batch/version_1_trial_traces/easy_fatem_111_t0.jsonl` |
| `canonical/easy_fatem_111_t1` | deep | unsolved | 20 | none | `7bd8303958e1` | `data/batch/version_1_trial_traces/easy_fatem_111_t1.jsonl` |
| `canonical/easy_fatem_111_t2` | deep | unsolved | 22 | none | `24d868e23e93` | `data/batch/version_1_trial_traces/easy_fatem_111_t2.jsonl` |
| `canonical/easy_fatem_111_t3` | deep | unsolved | 22 | none | `1e76ec174a20` | `data/batch/version_1_trial_traces/easy_fatem_111_t3.jsonl` |
| `canonical/easy_fatem_111_t4` | deep | unsolved | 20 | none | `697b2b001eaf` | `data/batch/version_1_trial_traces/easy_fatem_111_t4.jsonl` |
| `canonical/easy_fatem_111_t5` | deep | unsolved | 26 | none | `f83465d3c86c` | `data/batch/version_1_trial_traces/easy_fatem_111_t5.jsonl` |
| `canonical/easy_fatem_111_t6` | deep | unsolved | 20 | none | `7ea5a2fe3239` | `data/batch/version_1_trial_traces/easy_fatem_111_t6.jsonl` |
| `canonical/easy_fatem_111_t7` | deep | unsolved | 22 | none | `12f53521e48b` | `data/batch/version_1_trial_traces/easy_fatem_111_t7.jsonl` |
| `canonical/easy_fatem_111_t8` | deep | unsolved | 20 | none | `247bd40bda6f` | `data/batch/version_1_trial_traces/easy_fatem_111_t8.jsonl` |
| `canonical/easy_fatem_111_t9` | deep | unsolved | 26 | none | `55e4597b6c39` | `data/batch/version_1_trial_traces/easy_fatem_111_t9.jsonl` |
| `canonical/easy_fatem_115_t0` | deep | unsolved | 26 | none | `43030233d70e` | `data/batch/version_1_trial_traces/easy_fatem_115_t0.jsonl` |
| `canonical/easy_fatem_115_t1` | deep | unsolved | 22 | none | `c75286b3bd35` | `data/batch/version_1_trial_traces/easy_fatem_115_t1.jsonl` |
| `canonical/easy_fatem_115_t2` | deep | silent failure | 26 | none | `4c676480f1d4` | `data/batch/version_1_trial_traces/easy_fatem_115_t2.jsonl` |
| `canonical/easy_fatem_115_t3` | deep | unsolved | 30 | none | `ccaddde7d652` | `data/batch/version_1_trial_traces/easy_fatem_115_t3.jsonl` |
| `canonical/easy_fatem_115_t4` | deep | silent failure | 14 | none | `07f6766cfa01` | `data/batch/version_1_trial_traces/easy_fatem_115_t4.jsonl` |
| `canonical/easy_fatem_115_t5` | deep | silent failure | 24 | none | `2be2e6466930` | `data/batch/version_1_trial_traces/easy_fatem_115_t5.jsonl` |
| `canonical/easy_fatem_115_t6` | deep | unsolved | 22 | none | `8a26a2354ae0` | `data/batch/version_1_trial_traces/easy_fatem_115_t6.jsonl` |
| `canonical/easy_fatem_115_t7` | deep | unsolved | 12 | none | `a463b85ca3a1` | `data/batch/version_1_trial_traces/easy_fatem_115_t7.jsonl` |
| `canonical/easy_fatem_115_t8` | deep | silent failure | 24 | none | `332856f7ac7a` | `data/batch/version_1_trial_traces/easy_fatem_115_t8.jsonl` |
| `canonical/easy_fatem_115_t9` | deep | unsolved | 22 | none | `6d7b89242786` | `data/batch/version_1_trial_traces/easy_fatem_115_t9.jsonl` |
| `canonical/easy_leancat_001_t0` | deep | unsolved | 30 | none | `ddd32fe725ba` | `data/batch/version_1_trial_traces/easy_leancat_001_t0.jsonl` |
| `canonical/easy_leancat_001_t1` | compact | solved | 30 | none | `5b8bd661672c` | `data/batch/version_1_trial_traces/easy_leancat_001_t1.jsonl` |
| `canonical/easy_leancat_001_t2` | compact | solved | 8 | none | `90dc3af20492` | `data/batch/version_1_trial_traces/easy_leancat_001_t2.jsonl` |
| `canonical/easy_leancat_001_t3` | deep | unsolved | 28 | none | `c3f27169e552` | `data/batch/version_1_trial_traces/easy_leancat_001_t3.jsonl` |
| `canonical/easy_leancat_001_t4` | compact | solved | 14 | none | `6bb4bdc19d4e` | `data/batch/version_1_trial_traces/easy_leancat_001_t4.jsonl` |
| `canonical/easy_leancat_001_t5` | deep | unsolved | 24 | none | `00c91b1ff381` | `data/batch/version_1_trial_traces/easy_leancat_001_t5.jsonl` |
| `canonical/easy_leancat_001_t6` | deep | unsolved | 30 | none | `4b69bbbe5199` | `data/batch/version_1_trial_traces/easy_leancat_001_t6.jsonl` |
| `canonical/easy_leancat_001_t7` | compact | solved | 20 | none | `c875e21a9546` | `data/batch/version_1_trial_traces/easy_leancat_001_t7.jsonl` |
| `canonical/easy_leancat_001_t8` | compact | solved | 12 | none | `d64928845a8a` | `data/batch/version_1_trial_traces/easy_leancat_001_t8.jsonl` |
| `canonical/easy_leancat_001_t9` | compact | solved | 24 | none | `63e04f9fdde8` | `data/batch/version_1_trial_traces/easy_leancat_001_t9.jsonl` |
| `canonical/easy_leancat_002_t0` | compact | solved | 14 | none | `f2db9b77ff82` | `data/batch/version_1_trial_traces/easy_leancat_002_t0.jsonl` |
| `canonical/easy_leancat_002_t1` | deep | unsolved | 12 | none | `07b2564ca89f` | `data/batch/version_1_trial_traces/easy_leancat_002_t1.jsonl` |
| `canonical/easy_leancat_002_t2` | compact | solved | 14 | none | `6b7a8f4b2518` | `data/batch/version_1_trial_traces/easy_leancat_002_t2.jsonl` |
| `canonical/easy_leancat_002_t3` | compact | solved | 12 | none | `775d1e327edb` | `data/batch/version_1_trial_traces/easy_leancat_002_t3.jsonl` |
| `canonical/easy_leancat_002_t4` | compact | solved | 12 | none | `f50966791019` | `data/batch/version_1_trial_traces/easy_leancat_002_t4.jsonl` |
| `canonical/easy_leancat_002_t5` | compact | solved | 12 | none | `10c20738a1fb` | `data/batch/version_1_trial_traces/easy_leancat_002_t5.jsonl` |
| `canonical/easy_leancat_002_t6` | compact | solved | 12 | none | `74a54f279728` | `data/batch/version_1_trial_traces/easy_leancat_002_t6.jsonl` |
| `canonical/easy_leancat_002_t7` | compact | solved | 14 | none | `a1dd2a51f8d7` | `data/batch/version_1_trial_traces/easy_leancat_002_t7.jsonl` |
| `canonical/easy_leancat_002_t8` | compact | solved | 14 | none | `ebd1756181f9` | `data/batch/version_1_trial_traces/easy_leancat_002_t8.jsonl` |
| `canonical/easy_leancat_002_t9` | compact | solved | 16 | none | `de2357ca5824` | `data/batch/version_1_trial_traces/easy_leancat_002_t9.jsonl` |
| `recovery/easy_fatem_011_t0` | compact | historical solved | 10 | none | `66a4f028bfa2` | `data/experiments/qwen_recovery_triangle_v1/easy_fatem_011_t0.jsonl` |
| `recovery/easy_fatem_012_t0` | deep | historical silent failure; current unknown | 22 | none | `f3ce6b37ac33` | `data/experiments/qwen_recovery_triangle_v1/easy_fatem_012_t0.jsonl` |
| `recovery/easy_fatem_019_t0` | deep | unsolved | 28 | none | `3458678ded4c` | `data/experiments/qwen_recovery_triangle_v1/easy_fatem_019_t0.jsonl` |
| `recovery/easy_fatem_020_t0` | compact | historical solved | 16 | none | `8b348dad0591` | `data/experiments/qwen_recovery_triangle_v1/easy_fatem_020_t0.jsonl` |
| `recovery/easy_fatem_041_t0` | compact | historical solved | 8 | none | `241dbaa8bfc9` | `data/experiments/qwen_recovery_triangle_v1/easy_fatem_041_t0.jsonl` |
| `recovery/easy_fatem_109_t0` | deep | historical silent failure; current unknown | 14 | none | `2ce94fefa6ba` | `data/experiments/qwen_recovery_triangle_v1/easy_fatem_109_t0.jsonl` |
| `recovery/easy_fatem_111_t0` | compact | historical solved | 20 | none | `b557f34c7ed2` | `data/experiments/qwen_recovery_triangle_v1/easy_fatem_111_t0.jsonl` |
| `recovery/easy_fatem_115_t0` | deep | unsolved | 30 | none | `d5fbf1a1fc44` | `data/experiments/qwen_recovery_triangle_v1/easy_fatem_115_t0.jsonl` |
| `recovery/easy_leancat_001_t0` | compact | historical solved | 10 | none | `395033f8127a` | `data/experiments/qwen_recovery_triangle_v1/easy_leancat_001_t0.jsonl` |
| `recovery/easy_leancat_002_t0` | compact | historical solved | 10 | none | `13dcdd10bb6e` | `data/experiments/qwen_recovery_triangle_v1/easy_leancat_002_t0.jsonl` |
| `tool-routed/easy_fatem_115_t0` | deep | unsolved | 24 | none | `0364692b77c7` | `data/experiments/qwen_tool_routed_subgoals_v1/easy_fatem_115_t0.jsonl` |
| `tool-routed/easy_fatem_115_t1` | deep | unsolved | 80 | none | `c2684ff74712` | `data/experiments/qwen_tool_routed_subgoals_v1/easy_fatem_115_t1.jsonl` |
| `tool-routed/easy_fatem_115_t2` | deep | silent failure | 75 | none | `ce1292a55f5e` | `data/experiments/qwen_tool_routed_subgoals_v1/easy_fatem_115_t2.jsonl` |
| `tool-routed-aborted/easy_fatem_115_t0` | deep | interrupted | 47 | none | `7af4e0d2a865` | `data/experiments/qwen_tool_routed_subgoals_v1/aborted/easy_fatem_115_t0_interrupted_import_audit.jsonl` |
| `medium/medium_leancat_008_t0` | deep | unsolved | 202 | cap | `338d6e0d19b4` | `data/batch/qwen_medium_subgoals_v1/medium_leancat_008_t0.jsonl` |
| `medium/medium_leancat_008_t1` | deep | unsolved | 202 | cap | `a5aa4a28174b` | `data/batch/qwen_medium_subgoals_v1/medium_leancat_008_t1.jsonl` |
| `medium/medium_leancat_008_t2` | deep | unsolved | 147 | stuck | `885d45b87966` | `data/batch/qwen_medium_subgoals_v1/medium_leancat_008_t2.jsonl` |
| `medium/medium_leancat_008_t3` | deep | unsolved | 202 | cap | `1f7961746adb` | `data/batch/qwen_medium_subgoals_v1/medium_leancat_008_t3.jsonl` |
| `medium/medium_leancat_008_t4` | deep | unsolved | 202 | cap | `8480e03b6660` | `data/batch/qwen_medium_subgoals_v1/medium_leancat_008_t4.jsonl` |
| `medium/medium_leancat_008_t5` | deep | unsolved | 202 | cap | `0ec978ba5418` | `data/batch/qwen_medium_subgoals_v1/medium_leancat_008_t5.jsonl` |
| `medium/medium_leancat_008_t6` | deep | unsolved | 202 | cap | `24d3bf38eeb7` | `data/batch/qwen_medium_subgoals_v1/medium_leancat_008_t6.jsonl` |
| `medium/medium_leancat_008_t7` | deep | unsolved | 151 | stuck | `8d80b9dab5e2` | `data/batch/qwen_medium_subgoals_v1/medium_leancat_008_t7.jsonl` |
| `medium/medium_leancat_008_t8` | deep | unsolved | 116 | stuck | `5c73c13885d3` | `data/batch/qwen_medium_subgoals_v1/medium_leancat_008_t8.jsonl` |
| `medium/medium_leancat_008_t9` | deep | unsolved | 202 | cap | `d7caf1adecff` | `data/batch/qwen_medium_subgoals_v1/medium_leancat_008_t9.jsonl` |

### Reproduction Commands

Run from the repository root. These commands read data; they do not rerun an
agent or call an external API.

```powershell
# Inventory the research traces (exclude pytest fixtures).
Get-ChildItem data\batch\version_1_trial_traces -Filter *.jsonl -File
Get-ChildItem data\batch\qwen_medium_subgoals_v1 -Filter *.jsonl -File

# Validate every canonical record and its references.
python -m pytest tests\scripts\test_analyze_lean_easy_failures.py -q `
  -p no:cacheprovider --basetemp .pytest-basetemp-behavior-report

# Recompute a source hash.
Get-FileHash -Algorithm SHA256 `
  data\batch\version_1_trial_traces\easy_fatem_115_t2.jsonl

# Inspect one trace without changing it.
$env:PYTHONPATH = "src"
python -c "from traj_eval.trace_core.storage import read_trial; m,e=read_trial(r'data\batch\version_1_trial_traces\easy_fatem_115_t2.jsonl'); print(m.trial_id, len(e))"
```

### Limitations

- The canonical reviews are agent-reviewed, not independent expert gold.
- Historical traces lack explicit terminal events and raw anchor labels.
- The experimental summary labels were not freshly kernel-reconfirmed because
  the local strict audit produced no verdict in the available time.
- The medium sample is ten completed trials of one task and one backbone/setup,
  not a medium-tier or architecture-level performance estimate.
- No confidence calibration, matched baseline, stress progression, paired
  bootstrap, or detector precision/recall is reported here.
- The report localizes visible failures to events and roles. It does not explain
  model-level internal causes.
