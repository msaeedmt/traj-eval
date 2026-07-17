# Lean V1-V3 failure-mode analysis

## Research question

Do the teammate's kernel-backed goal tools and the existing subgoal-DAG
controller improve Lean proof success, or do they mainly improve failure
localization? This report classifies all 123 currently preserved JSONL traces:
100 V1 traces, 20 V2 traces and 3 V3 traces. Interrupted traces remain evidence
but are excluded from completed-trial success denominators.

## Evidence inventory

| Version | Scope | Completed outcome evidence | Main intervention |
|---|---:|---|---|
| V1 | 100 traces, 10 tasks x 10 | 56 solved, 40 unsolved, 4 silent failures | `search_lemmas` + `check_lean` baseline |
| V2 | 20 traces | FATE-M 019: 0/10; FATE-M 020: 2/7 plus one interrupted; one completed and one interrupted 200-turn diagnostic | add `try_tactic` + `show_goals` |
| V3 | 3 traces | matched clean pair both unsolved; one extra interrupted pilot | typed subgoal DAG, then DAG plus goal tools |

V2 is not a 100-trial replication of V1. Its task mix is deliberately
failure-focused, so its aggregate success rate must not be compared with V1's
overall 56%. The valid within-task comparisons are below.

## Matched findings

| Task and condition | Result | What changed |
|---|---|---|
| FATE-M 019, V1 baseline | 0/10 | repeated retrieval, sparse Lean attempts, no accepted target proof |
| FATE-M 019, V2 goal tools, 30 turns | 0/10 | the available tools were never reached; all trials stayed with Reasoner retrieval |
| FATE-M 019, V2 200-turn diagnostic | 0/1 completed | more turns alone did not cross the Reasoner routing barrier |
| FATE-M 019, V3 DAG only, 200 turns | 0/1 | DAG crossed the routing barrier and forced real Lean work, but capped after 24 failed checks and one successful probe |
| FATE-M 019, V3 DAG plus goal tools | 0/1 | `try_tactic` was used three times and a candidate reached review, but repeated retrieval caused a `stuck` stop; `show_goals` was unused |
| FATE-M 020, V1 baseline | 3/10 | baseline already sometimes solves the ideal theorem |
| FATE-M 020, V2 completed subset | 2/7 | 28.6% versus V1's 30% is descriptively similar and statistically inconclusive |

The two V3 `t1` arms are structurally matched. Their only Engineer permission
difference is `try_tactic` and `show_goals`. Both use the same Qwen model,
thinking disabled, 1,500-token call cap, 180-second request timeout, theorem,
200-turn budget, DAG limits and kernel validator.

## Failure-mode classification

### 1. Routing starvation

The strongest V2 failure is architectural: all ten FATE-M 019 trials made only
Reasoner `search_lemmas` calls. The new goal tools could not help because
Engineer never received control. Increasing the budget to 200 turns did not
repair this. Tool availability must therefore be separated from tool reachability.

### 2. Retrieval loops and no-progress termination

Near-duplicate searches dominate the failed traces. V3's typed controller
crossed the first routing barrier, but both arms still revisited the same ZMod
field/primality queries. In the combined arm the identical-call guard correctly
terminated the loop as `stuck`, which is safer and easier to diagnose than an
unbounded run.

### 3. Mathlib API and typeclass errors

The recurrent kernel failures are unknown constants, typeclass-resolution
failure and application-type mismatch. Typical examples include attempts to
use unavailable names such as `ZMod.instField` or
`Finite.isField_of_domain`, and treating `IsField` as a typeclass. The V1
reviewed taxonomy already identifies unknown-symbol, typeclass and application
mismatch failures; V3 makes their repetition within a subgoal explicit.

### 4. Probe success mistaken for proof progress

V3 DAG-only recorded successful compiler probes, but none established the
target or produced critic acceptance. This confirms why probe, subgoal and
final purposes must remain distinct. A green `#check` or helper example is not
a successful theorem proof.

### 5. Candidate and critic gating

The combined V3 arm advanced farther operationally: a successful candidate was
submitted and critic-side review tools ran. It still had no accepted final
artifact. The DAG therefore improves evidence ownership and exposes where the
workflow stopped, without establishing higher task success.

### 6. Goal-tool selection

`try_tactic` was selected once in V2 FATE-M 020 and three times in the V3
combined arm; none of those trials solved. `show_goals` was selected once in an
unsolved V2 trial and never in the V3 matched arm. This is evidence about model
tool selection, not evidence that the tools are intrinsically ineffective.
Their deterministic Lean tests still demonstrate correct kernel-backed
behavior on suitable local goals.

### 7. Provider and runtime failures

One V2 200-turn trace captures the Qwen thinking/prefill incompatibility. The
V3 `t0` pilot captures a long provider response and manual interruption. These
events motivated explicit non-thinking requests, a 1,500-token output cap and
a 180-second request timeout. They must not be counted as mathematical failures.

## Strengths and drawbacks

Strengths:

- The V3 pair is a real matched intervention, not a wholesale runtime swap.
- Lean kernel results distinguish compilation, probes and accepted artifacts.
- The DAG crosses the V2 routing barrier and records graph revisions, bounded
  recovery, terminal reasons and critic ownership.
- Runtime caps prevent provider behavior from silently consuming unlimited
  time or output.

Drawbacks:

- The matched evidence is one theorem, one model and one completed trial per arm.
- Both arms remain sensitive to Qwen's repetitive retrieval behavior.
- The DAG adds substantial controller, state and test surface; it is useful as
  a named experimental setup, not yet justified as the default Lean runtime.
- `try_tactic` and `show_goals` help only after the model reaches Engineer and
  chooses them appropriately.
- Residual AG2/provider wrapper behavior remains part of the measurement.

## Educational conclusion and claim boundary

The current evidence supports three claims: the old setup has a routing
starvation failure, the DAG improves failure localization and tool
reachability, and bounded runtime controls improve experimental safety. It does
not show that either the DAG or the two goal tools improve Lean success rate.
For FATE-M 020, V2's 2/7 completed subset is descriptively close to V1's 3/10;
for FATE-M 019 every completed condition remains unsolved.

For the broader NLP proposal, these components are useful as instrumentation
and controlled failure interventions. They do not establish overall proposal
quality or general agent benefit. That would require repeated matched trials,
confidence intervals, a single-agent control, more theorems, and separate
measurement of routing, tool selection and final kernel-verified success.

The public default remains `recovery_triangle_v1`. Keep the DAG as an explicit
experimental setup until replicated evidence justifies promoting it.
