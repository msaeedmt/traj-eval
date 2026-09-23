# Experiment batches

One folder per experiment configuration. Each folder holds a `config.json`
describing exactly how it was run and one JSONL trace per trial, named
`<task_id>_t<trial>.jsonl` (line 0 = `TrialMeta`, lines 1..n = `TraceEvent`s;
schema in `../../schema/`). Traces are never edited after a run; every number
in the report is recomputed from them by `scripts/analyse_astro_trials.py`,
`scripts/analyze_batch.py` and `scripts/compare_offline_kernel.py`. Derived
summaries live in `../analysis/`.

## Lean — model matrix (`lean-anchor-engineer-model-matrix-v1`)

Fixed: 20 tasks (10 easy: FATE-M + LeanCat; 10 medium: FATE-H + LeanCat),
temperature 0.2, 30 routing turns, role token budgets 2048/4096/2048, the
`recovery_triangle_v1` prompts, the same runtime commit for every arm. Only
the models change.

| folder | phase | reasoner / engineer / critic | trials | traces |
|---|---|---|--:|--:|
| `pilot_A1_gpt54_all_roles` | pilot | gpt-5.4 / gpt-5.4 / gpt-5.4 | 20 × 3 | 60 |
| `pilot_A2_gpt54mini_all_roles` | pilot | gpt-5.4-mini ×3 | 20 × 3 | 60 |
| `pilot_A3_codestral_all_roles` | pilot | codestral-2508 ×3 | 20 × 3 | 60 |
| `pilot_A4_devstral_all_roles` | pilot | devstral-2512 ×3 | 20 × 3 | 60 |
| `pilot_B1_gpt54_codestral_critic` | pilot | gpt-5.4 / gpt-5.4 / **codestral** | 20 × 3 | 60 |
| `confirm_A1_gpt54_all_roles` | paired confirmation | gpt-5.4 ×3 | 20 × 10 | 154 / 200 |
| `confirm_B1_gpt54_codestral_critic` | paired confirmation | gpt-5.4 / gpt-5.4 / **codestral** | 20 × 10 | 154 / 200 |

A1 vs B1 is the controlled critic ablation: identical reasoner, engineer,
tasks, budgets and tools; only the critic's model differs. The two
confirmation arms are missing the *same* 46 traces (quota exhaustion at the
end of the schedule: `medium_fateh_013`, `medium_fateh_097`,
`medium_leancat_008`, `medium_leancat_021` absent, `medium_fateh_012` at
4/10), so the A1/B1 pairing is intact but absolute confirmation rates cover
16 tasks rather than 20. Outcomes are near-deterministic per task (≈80% of
task cells are 0/10 or 10/10), so the effective sample for any statistical
claim is the number of tasks, not trials.

Success is defined out-of-loop: the submitted proof must compile, be
sorry-free, prove the exact intended statement and depend on no axiom beyond
`propext`, `Classical.choice`, `Quot.sound` (`metrics/lean/validator.py`).

### Historical Lean batches (different runner and prompts; not comparable)

| folder | contents |
|---|---|
| `version_1_trial_traces` | Qwen3.5-27B, 10 easy tasks × 10 trials, `search_lemmas` + `check_lean` only |
| `version_2_trial_traces` | Qwen3.5-27B, after adding `try_tactic` / `show_goals`; 18 trials on two tasks (+ a `200_turns/` diagnostic) |
| `version_3_trial_traces` | Qwen3.5-27B, subgoal-DAG ablation on `easy_fatem_019`; 3 traces in `dag_only/` and `dag_plus_goal_tools/` |

Kept as provenance for the midterm results; not used in the final analysis.

## Astro — Stargazer synthetic bank

Roles planner / engineer / critic; only the critic holds `rv_submit`. Turn and
submission budgets are per tier (easy 30 turns / 3 attempts, medium 50 / 5,
hard 60–90 / 10; see each trace's `TrialMeta.config`).

| folder | backbone | tiers | task filter | match threshold | trials | traces | controller bounds |
|---|---|---|---|---|--:|--:|---|
| `astro_gpt54_all3_20260831T171502578Z_8c6ef41a_synthetic` | gpt-5.4 | easy, medium *(hard planned, run cut short)* | none (49 of 100 tasks reached) | 0.80 (Stargazer default) | 3 | 145 | **none** — run before the idle / no-submission / cycle bounds existed |
| `astro_easy_medium_hard_gpt-4o-mini_t1` | gpt-4o-mini | easy, medium, hard | ≥1 planet, solvable at 0.512 | 0.512 (`--tolerance 3`) | 1 | 56 | active |
| `astro_medium_hard_gpt-4o_t1` | gpt-4o | medium, hard | ≥2 planets, solvable at 0.512 | 0.512 | 1 | 12 / 16 | active |
| `astro_medium_hard_openai-gpt-5.4-mini-2026-03-17_t1` | gpt-5.4-mini | medium, hard | ≥2 planets, solvable at 0.512 | 0.512 | 1 | 16 | active |

**Read this before comparing astro batches.** The four batches differ in task
set, difficulty, match threshold and stopping rules, so pass rates are not
comparable across them. In particular the identical-call bound (added in
commit `dc052a2`, after the gpt-5.4 run) terminated 23 of the 56 gpt-4o-mini
runs, 16 of them while the critic was re-running a check another role had
already made; those runs ended with submission attempts unused for reasons
partly set by the instrument. The report therefore compares *behaviour within
a batch* (who held the turn, what the critic did after a failed submission,
whether a passing system existed among the team's own fits) and uses only the
12 tasks shared by the gpt-4o and gpt-5.4-mini batches for a matched pass-rate
comparison. `scripts/analyse_astro_trials.py` re-scores every batch from the
recorded per-submission measurements, so any threshold can be applied
uniformly after the fact.

A run over the 20 real archival systems was planned (config only); no traces
were produced.

## Provenance

Lean traces are byte-identical to the original run output; the original
Run/Restart layout (including quota-error artefacts and restart duplicates)
is preserved in commit `1dd06c485df34a10db990f051972d7b190e7946e` of the
`han-lean-anchors-merge` branch. Each Lean folder's `config.json` records the
runtime commit, prompt blob, dataset tree and model IDs it was run with.
