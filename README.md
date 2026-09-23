# traj-eval

Trajectory-level evaluation of multi-agent scientific reasoning.

NLP Lab · CAISA Lab · University of Bonn · Summer Semester 2026
Jiadong Han · Mohammad Saeed Motevali Amin

## What this is

A pass rate says *whether* a team of agents failed, not *where*. This
repository records every move a three-role agent team makes (plan → build &
check → review), judges the result afterwards with a checker the agents never
ran, and counts failures directly from the recorded moves — no LLM judge. The
same team design is instantiated on two testbeds:

| testbed | task | roles | in-loop checker the agents see | independent judge |
|---|---|---|---|---|
| **Lean 4** | prove a theorem (FATE / LeanCat) | reasoner → engineer ⇄ critic | `check_lean`: compiles? sorry-free? — not *which* theorem, not *which* axioms | Lean kernel + exact-statement check + `#print axioms` |
| **Astro** | recover a planetary system from radial-velocity data (Stargazer) | planner → engineer ⇄ critic | `rv_submit`: pass/fail per criterion, attempts capped; only the critic holds it | Stargazer forward model, scored over every subset of the team's own fits |

Agents choose their own next action (a `HANDOFF:` / `VERDICT:` marker line or
a native tool call); a domain-agnostic controller validates the choice against
the domain's allowed-move graph and records why each run ended
(`clean` / `cap` / `stuck…`). That is what makes coordination a measured,
fallible decision rather than a hard-coded pipeline.

## Headline results

Five backbones on the same 20 Lean tasks (10 easy, 10 medium), 608 trials;
four backbones on the Stargazer synthetic bank, 229 trials. Trace-derived
numbers below come from `data/batch` via the scripts in `scripts/`; the kernel
figures additionally need a built Mathlib project (`docs/SETUP.md`).

**Failure changes character with capability.**

| Lean arm | delivered proofs | first compile clean | delivered after a failed first compile | runs ending `stuck` |
|---|--:|--:|--:|--:|
| codestral, all roles | 3% | 0% | 4% | 83% |
| devstral, all roles | 12% | 12% | 2% | 72% |
| gpt-5.4-mini, all roles | 40% | 27% | 20% | 18% |
| gpt-5.4, all roles | 75% | 49% | 55% | 3% |

Weak teams fail the *protocol* (invalid hand-offs, tool calls typed as prose,
markers emitted as tool names) and rarely recover from a bad start. Above that
threshold protocol errors vanish and what remains is coordination.

**Knowing is not delivering.** In both domains, teams hold an independently
verified answer and fail to deliver it: 3% of verified answers at the frontier
(gpt-5.4, Lean and astro), 25% for the weaker astro teams. All 24 lost Lean
proofs pass the full kernel gate, and they span weak, middle and frontier teams.

**The critic is the coordination role, and it fails in two directions.** The
gpt-5.4 critic issues 156 verdicts, all approvals, and re-checks 153 of the 159
runs where it acts without finding a single error. Across the weaker and mixed
arms, 25 runs carry a non-approval critic message; 23 of those already held an
accepted check, and all 23 pass the kernel gate — not one rejection removed a
bad proof. Swapping *only* the critic: accepted checks 161 → 159, delivered
97% → 91% of those, lost answers 5 → 15. Task-clustered 95% CI on the
delivery gap is [−3, +16] pp — directional, not significant at 20 tasks;
the mechanism is not in doubt.

**Where the roles were used.** An explicit engineer→planner hand-back appears
in 18 of 27 solved two-planet astro runs and 0 of 114 solved one-planet runs;
the review step caught nothing in either domain. No astro run ever exhausted
its submission budget (0/229).

Full tables, per-batch configurations and confounds are in
`data/batch/README.md` and `docs/final-report.pdf`.

## Layout

```
src/traj_eval/
  trace_core/        schema (TraceEvent, TrialMeta), JSONL storage, causal graph
  agents/            free-routing controller, observer, routing ledger,
                     Lean team + roles, astro team + roles, LLM config
  tools/             check_lean / search_lemmas / try_tactic / show_goals;
                     rv_periodogram / rv_fit / rv_residual / rv_submit
  metrics/lean/      artifact extraction, offline kernel validator, batch report
  metrics/astro/     artifacts, criteria, evaluate, oracle (counterfactual),
                     sequence, ceiling, idle, validator, batch report
  anchors/astro/     period-selection anchor (alias / harmonic / window labels)
  detectors/         perseveration detector
  dataset/           MiniFATELeanCat loader; Stargazer bank + loader
  dashboard/         Streamlit batch/trial viewer (Lean)
  vendor/stargazer/  vendored scoring subset of Stargazer (MIT), with provenance
schema/              exported JSON Schema for trace events and trial meta
scripts/             batch runners and offline analysis (see Reproduce)
dataset/             the two benchmarks (tracked)
data/batch/          one folder per experiment configuration (traces, config)
data/analysis/       derived per-batch summaries (generated, not tracked)
tests/               311 pytest tests; core suite needs no API key and no Lean
docs/SETUP.md        environment, model access, Lean toolchain
docs/final-report.pdf        the report these results are drawn from
docs/final-presentation.pptx the accompanying talk
```

## Reproduce

Environment: `docs/SETUP.md`. Offline analysis needs only `uv sync`; running
trials needs `--all-extras`, an API key, and (for Lean) a built Mathlib project.

**Lean**

```bash
# one problem, end to end
TRAJ_EVAL_MODEL=gpt-5.4 uv run python scripts/run_dataset_task.py easy_fatem_011

# a batch: N trials per problem over difficulty tiers → data/batch/<batch>/
TRAJ_EVAL_MODEL=gpt-5.4 uv run python scripts/run_batch.py --difficulty easy medium --trials 3

# offline: per-task success from the traces (fast), then kernel re-verification
uv run python scripts/analyze_batch.py data/batch/pilot_A1_gpt54_all_roles
uv run python scripts/analyze_batch.py data/batch/pilot_A1_gpt54_all_roles --validate
uv run python scripts/compare_offline_kernel.py data/batch/pilot_A1_gpt54_all_roles

# dashboard
uv run streamlit run src/traj_eval/dashboard/app.py
```

The five-arm Lean model matrix in `data/batch/{pilot,confirm}_*` was run with
role-specific models (see each folder's `config.json`); `run_batch.py` takes
one backbone via `TRAJ_EVAL_MODEL`.

**Astro**

```bash
# one task
TRAJ_EVAL_MODEL=gpt-4o-mini uv run python scripts/run_astro_task.py seed1108_diff2

# a batch over tiers, with the filters used for the later runs
TRAJ_EVAL_MODEL=gpt-4o uv run python scripts/run_astro_batch.py \
    --tier medium hard --trials 1 --min-planets 2 --solvable-only --tolerance 3

# offline: Stargazer-comparable outcomes, trajectory metrics, silent-failure
# flags, counterfactual oracle, period anchor
uv run python scripts/analyse_astro_trials.py data/batch/astro_medium_hard_gpt-4o_t1 \
    --json data/analysis/astro_medium_hard_gpt-4o_t1_summary.json

# supporting caches
uv run python scripts/compute_match_ceilings.py        # dataset/Astro/ceilings.json
uv run python scripts/analyse_idle_runs.py data/batch/<batch>
```

Two things to know before comparing astro batches: the gpt-5.4 batch was run
at Stargazer's 0.80 match threshold on 49 easy/medium tasks and *before* the
controller's idle / no-submission bounds existed; the three later batches were
run at a relaxed threshold (`--tolerance 3` ⇒ 0.512) on filtered task sets
with those bounds active. Compare behaviour within a batch, not pass rates
across batches. `data/batch/README.md` lists every batch with its
configuration.

## Relation to the proposal

* **O1 — localisation infrastructure:** delivered. Non-invasive observer,
  schema-validated event log with causal edges, reason-tagged termination,
  offline validators on both testbeds, Lean dashboard.
* **O2 — failure taxonomy and detectors:** delivered in part. Perseveration
  detector, period-selection anchor (alias / harmonic / window), seven astro
  silent-failure flags, Lean statement / axiom checks. Of the astro flags,
  only alias convergence discriminates outcomes once task difficulty is
  controlled; the rest are reported as non-diagnostic.
* **O3 — early prediction under stress:** not run. The stress ladder and the
  single-agent baseline were not executed; the one early signal we do have is
  that the outcome of the first verification event predicts delivery.

## Benchmarks and upstream code

* FATE — Jiang et al., *FATE: A Formal Benchmark Series for Frontier Algebra*, 2025.
* LeanCat — Xu et al., *LeanCat: A Benchmark Suite for Formal Category Theory in Lean*, 2025.
* Stargazer — Liu et al., *Stargazer: A Scalable Model-Fitting Benchmark Environment for AI Agents under Astrophysical Constraints*, 2026. Scoring code vendored under `src/traj_eval/vendor/stargazer/` (MIT; see `PROVENANCE.md`).
* Agent substrate: AG2 / AutoGen.
