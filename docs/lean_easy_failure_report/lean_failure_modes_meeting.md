# Lean failure and recovery traces

> Meeting report generated from the same validated bundle as the offline dashboard. Raw JSONL records remain separate from reviewed classifications and reconstructed progress.

## Evidence scope

| Complete trace cohort | Trials |
|---|---:|
| Easy failures | 44 |
| Medium failures with subgoal tools | 20 |
| Recovery successes | 17 |
| One-shot contrast | 1 |
| **Total** | **82** |

The bundle contains **4,430 events** and **4,311 causal edges**. Open [the interactive offline dashboard](lean_failure_modes_meeting.html) to inspect exact source records, synchronized role graphs, Lean checks, and event payloads.

## Recovery after compiler failure

A recovery is a kernel-confirmed exact-target run where at least one failed compiler result precedes the terminal selected exact-target acceptance. This includes a run that compiled early, regressed, and later recovered.

**17 complete recovery traces.** Use [easy_fatem_011_t0](lean_failure_modes_meeting.html#trial=easy_fatem_011_t0&event=0&view=trace) as the one-shot contrast.

| Task | Trial | Recovery path |
|---|---|---|
| easy_fatem_012 | [easy_fatem_012_t0](lean_failure_modes_meeting.html#trial=easy_fatem_012_t0&event=7&view=trace) | 3 failed checks; [first failure #7](lean_failure_modes_meeting.html#trial=easy_fatem_012_t0&event=7&view=trace) → [last failure #11](lean_failure_modes_meeting.html#trial=easy_fatem_012_t0&event=11&view=trace) → [accepted #16](lean_failure_modes_meeting.html#trial=easy_fatem_012_t0&event=16&view=trace). |
| easy_fatem_012 | [easy_fatem_012_t1](lean_failure_modes_meeting.html#trial=easy_fatem_012_t1&event=9&view=trace) | 2 failed checks; [first failure #9](lean_failure_modes_meeting.html#trial=easy_fatem_012_t1&event=9&view=trace) → [last failure #11](lean_failure_modes_meeting.html#trial=easy_fatem_012_t1&event=11&view=trace) → [accepted #17](lean_failure_modes_meeting.html#trial=easy_fatem_012_t1&event=17&view=trace). Earlier pass, regression, then terminal recovery. |
| easy_fatem_012 | [easy_fatem_012_t2](lean_failure_modes_meeting.html#trial=easy_fatem_012_t2&event=5&view=trace) | 2 failed checks; [first failure #5](lean_failure_modes_meeting.html#trial=easy_fatem_012_t2&event=5&view=trace) → [last failure #7](lean_failure_modes_meeting.html#trial=easy_fatem_012_t2&event=7&view=trace) → [accepted #11](lean_failure_modes_meeting.html#trial=easy_fatem_012_t2&event=11&view=trace). |
| easy_fatem_012 | [easy_fatem_012_t3](lean_failure_modes_meeting.html#trial=easy_fatem_012_t3&event=7&view=trace) | 3 failed checks; [first failure #7](lean_failure_modes_meeting.html#trial=easy_fatem_012_t3&event=7&view=trace) → [last failure #11](lean_failure_modes_meeting.html#trial=easy_fatem_012_t3&event=11&view=trace) → [accepted #18](lean_failure_modes_meeting.html#trial=easy_fatem_012_t3&event=18&view=trace). |
| easy_fatem_012 | [easy_fatem_012_t4](lean_failure_modes_meeting.html#trial=easy_fatem_012_t4&event=7&view=trace) | 2 failed checks; [first failure #7](lean_failure_modes_meeting.html#trial=easy_fatem_012_t4&event=7&view=trace) → [last failure #11](lean_failure_modes_meeting.html#trial=easy_fatem_012_t4&event=11&view=trace) → [accepted #13](lean_failure_modes_meeting.html#trial=easy_fatem_012_t4&event=13&view=trace). |
| easy_fatem_012 | [easy_fatem_012_t5](lean_failure_modes_meeting.html#trial=easy_fatem_012_t5&event=7&view=trace) | 5 failed checks; [first failure #7](lean_failure_modes_meeting.html#trial=easy_fatem_012_t5&event=7&view=trace) → [last failure #19](lean_failure_modes_meeting.html#trial=easy_fatem_012_t5&event=19&view=trace) → [accepted #23](lean_failure_modes_meeting.html#trial=easy_fatem_012_t5&event=23&view=trace). Earlier pass, regression, then terminal recovery. |
| easy_fatem_012 | [easy_fatem_012_t7](lean_failure_modes_meeting.html#trial=easy_fatem_012_t7&event=7&view=trace) | 1 failed check; [first failure #7](lean_failure_modes_meeting.html#trial=easy_fatem_012_t7&event=7&view=trace) → [last failure #7](lean_failure_modes_meeting.html#trial=easy_fatem_012_t7&event=7&view=trace) → [accepted #12](lean_failure_modes_meeting.html#trial=easy_fatem_012_t7&event=12&view=trace). |
| easy_fatem_012 | [easy_fatem_012_t8](lean_failure_modes_meeting.html#trial=easy_fatem_012_t8&event=7&view=trace) | 1 failed check; [first failure #7](lean_failure_modes_meeting.html#trial=easy_fatem_012_t8&event=7&view=trace) → [last failure #7](lean_failure_modes_meeting.html#trial=easy_fatem_012_t8&event=7&view=trace) → [accepted #12](lean_failure_modes_meeting.html#trial=easy_fatem_012_t8&event=12&view=trace). |
| easy_fatem_012 | [easy_fatem_012_t9](lean_failure_modes_meeting.html#trial=easy_fatem_012_t9&event=5&view=trace) | 1 failed check; [first failure #5](lean_failure_modes_meeting.html#trial=easy_fatem_012_t9&event=5&view=trace) → [last failure #5](lean_failure_modes_meeting.html#trial=easy_fatem_012_t9&event=5&view=trace) → [accepted #7](lean_failure_modes_meeting.html#trial=easy_fatem_012_t9&event=7&view=trace). |
| easy_fatem_020 | [easy_fatem_020_t0](lean_failure_modes_meeting.html#trial=easy_fatem_020_t0&event=7&view=trace) | 2 failed checks; [first failure #7](lean_failure_modes_meeting.html#trial=easy_fatem_020_t0&event=7&view=trace) → [last failure #9](lean_failure_modes_meeting.html#trial=easy_fatem_020_t0&event=9&view=trace) → [accepted #13](lean_failure_modes_meeting.html#trial=easy_fatem_020_t0&event=13&view=trace). |
| easy_fatem_020 | [easy_fatem_020_t1](lean_failure_modes_meeting.html#trial=easy_fatem_020_t1&event=5&view=trace) | 2 failed checks; [first failure #5](lean_failure_modes_meeting.html#trial=easy_fatem_020_t1&event=5&view=trace) → [last failure #7](lean_failure_modes_meeting.html#trial=easy_fatem_020_t1&event=7&view=trace) → [accepted #14](lean_failure_modes_meeting.html#trial=easy_fatem_020_t1&event=14&view=trace). |
| easy_leancat_001 | [easy_leancat_001_t1](lean_failure_modes_meeting.html#trial=easy_leancat_001_t1&event=15&view=trace) | 3 failed checks; [first failure #15](lean_failure_modes_meeting.html#trial=easy_leancat_001_t1&event=15&view=trace) → [last failure #27](lean_failure_modes_meeting.html#trial=easy_leancat_001_t1&event=27&view=trace) → [accepted #29](lean_failure_modes_meeting.html#trial=easy_leancat_001_t1&event=29&view=trace). Earlier pass, regression, then terminal recovery. |
| easy_leancat_001 | [easy_leancat_001_t7](lean_failure_modes_meeting.html#trial=easy_leancat_001_t7&event=11&view=trace) | 1 failed check; [first failure #11](lean_failure_modes_meeting.html#trial=easy_leancat_001_t7&event=11&view=trace) → [last failure #11](lean_failure_modes_meeting.html#trial=easy_leancat_001_t7&event=11&view=trace) → [accepted #17](lean_failure_modes_meeting.html#trial=easy_leancat_001_t7&event=17&view=trace). |
| easy_leancat_001 | [easy_leancat_001_t9](lean_failure_modes_meeting.html#trial=easy_leancat_001_t9&event=9&view=trace) | 1 failed check; [first failure #9](lean_failure_modes_meeting.html#trial=easy_leancat_001_t9&event=9&view=trace) → [last failure #9](lean_failure_modes_meeting.html#trial=easy_leancat_001_t9&event=9&view=trace) → [accepted #22](lean_failure_modes_meeting.html#trial=easy_leancat_001_t9&event=22&view=trace). |
| easy_leancat_002 | [easy_leancat_002_t4](lean_failure_modes_meeting.html#trial=easy_leancat_002_t4&event=5&view=trace) | 2 failed checks; [first failure #5](lean_failure_modes_meeting.html#trial=easy_leancat_002_t4&event=5&view=trace) → [last failure #7](lean_failure_modes_meeting.html#trial=easy_leancat_002_t4&event=7&view=trace) → [accepted #9](lean_failure_modes_meeting.html#trial=easy_leancat_002_t4&event=9&view=trace). |
| easy_leancat_002 | [easy_leancat_002_t7](lean_failure_modes_meeting.html#trial=easy_leancat_002_t7&event=7&view=trace) | 1 failed check; [first failure #7](lean_failure_modes_meeting.html#trial=easy_leancat_002_t7&event=7&view=trace) → [last failure #7](lean_failure_modes_meeting.html#trial=easy_leancat_002_t7&event=7&view=trace) → [accepted #12](lean_failure_modes_meeting.html#trial=easy_leancat_002_t7&event=12&view=trace). |
| easy_leancat_002 | [easy_leancat_002_t9](lean_failure_modes_meeting.html#trial=easy_leancat_002_t9&event=7&view=trace) | 1 failed check; [first failure #7](lean_failure_modes_meeting.html#trial=easy_leancat_002_t9&event=7&view=trace) → [last failure #7](lean_failure_modes_meeting.html#trial=easy_leancat_002_t9&event=7&view=trace) → [accepted #14](lean_failure_modes_meeting.html#trial=easy_leancat_002_t9&event=14&view=trace). |

## Easy failure modes

The 44 easy failures form a reviewed partition. Labels below are enrichments anchored to raw event evidence, not fields copied from the source JSONL.

| Reviewed failure mode | Count | Complete trace index |
|---|---:|---|
| Statement drift / false acceptance | 5 | [easy_fatem_115_t2](lean_failure_modes_meeting.html#trial=easy_fatem_115_t2&event=22&view=trace), [easy_fatem_115_t3](lean_failure_modes_meeting.html#trial=easy_fatem_115_t3&event=15&view=trace), [easy_fatem_115_t4](lean_failure_modes_meeting.html#trial=easy_fatem_115_t4&event=12&view=trace), [easy_fatem_115_t5](lean_failure_modes_meeting.html#trial=easy_fatem_115_t5&event=22&view=trace), [easy_fatem_115_t8](lean_failure_modes_meeting.html#trial=easy_fatem_115_t8&event=22&view=trace) |
| Opaque verifier feedback | 15 | [easy_fatem_019_t0](lean_failure_modes_meeting.html#trial=easy_fatem_019_t0&event=0&view=trace), [easy_fatem_111_t0](lean_failure_modes_meeting.html#trial=easy_fatem_111_t0&event=23&view=trace), [easy_fatem_111_t1](lean_failure_modes_meeting.html#trial=easy_fatem_111_t1&event=0&view=trace), [easy_fatem_111_t2](lean_failure_modes_meeting.html#trial=easy_fatem_111_t2&event=0&view=trace), [easy_fatem_111_t3](lean_failure_modes_meeting.html#trial=easy_fatem_111_t3&event=0&view=trace), [easy_fatem_111_t4](lean_failure_modes_meeting.html#trial=easy_fatem_111_t4&event=0&view=trace), [easy_fatem_111_t5](lean_failure_modes_meeting.html#trial=easy_fatem_111_t5&event=0&view=trace), [easy_fatem_111_t6](lean_failure_modes_meeting.html#trial=easy_fatem_111_t6&event=0&view=trace), [easy_fatem_111_t7](lean_failure_modes_meeting.html#trial=easy_fatem_111_t7&event=0&view=trace), [easy_fatem_111_t8](lean_failure_modes_meeting.html#trial=easy_fatem_111_t8&event=0&view=trace), [easy_fatem_111_t9](lean_failure_modes_meeting.html#trial=easy_fatem_111_t9&event=0&view=trace), [easy_leancat_001_t0](lean_failure_modes_meeting.html#trial=easy_leancat_001_t0&event=21&view=trace), [easy_leancat_001_t3](lean_failure_modes_meeting.html#trial=easy_leancat_001_t3&event=0&view=trace), [easy_leancat_001_t5](lean_failure_modes_meeting.html#trial=easy_leancat_001_t5&event=0&view=trace), [easy_leancat_001_t6](lean_failure_modes_meeting.html#trial=easy_leancat_001_t6&event=29&view=trace) |
| Application / type mismatch | 7 | [easy_fatem_019_t2](lean_failure_modes_meeting.html#trial=easy_fatem_019_t2&event=25&view=trace), [easy_fatem_020_t9](lean_failure_modes_meeting.html#trial=easy_fatem_020_t9&event=0&view=trace), [easy_fatem_115_t0](lean_failure_modes_meeting.html#trial=easy_fatem_115_t0&event=0&view=trace), [easy_fatem_115_t1](lean_failure_modes_meeting.html#trial=easy_fatem_115_t1&event=0&view=trace), [easy_fatem_115_t6](lean_failure_modes_meeting.html#trial=easy_fatem_115_t6&event=0&view=trace), [easy_fatem_115_t7](lean_failure_modes_meeting.html#trial=easy_fatem_115_t7&event=0&view=trace), [easy_fatem_115_t9](lean_failure_modes_meeting.html#trial=easy_fatem_115_t9&event=0&view=trace) |
| Typeclass-resolution failure | 6 | [easy_fatem_019_t6](lean_failure_modes_meeting.html#trial=easy_fatem_019_t6&event=0&view=trace), [easy_fatem_020_t2](lean_failure_modes_meeting.html#trial=easy_fatem_020_t2&event=0&view=trace), [easy_fatem_020_t4](lean_failure_modes_meeting.html#trial=easy_fatem_020_t4&event=0&view=trace), [easy_fatem_020_t5](lean_failure_modes_meeting.html#trial=easy_fatem_020_t5&event=0&view=trace), [easy_fatem_020_t7](lean_failure_modes_meeting.html#trial=easy_fatem_020_t7&event=0&view=trace), [easy_fatem_020_t8](lean_failure_modes_meeting.html#trial=easy_fatem_020_t8&event=27&view=trace) |
| Unknown Mathlib symbol / API | 5 | [easy_fatem_019_t1](lean_failure_modes_meeting.html#trial=easy_fatem_019_t1&event=0&view=trace), [easy_fatem_019_t3](lean_failure_modes_meeting.html#trial=easy_fatem_019_t3&event=0&view=trace), [easy_fatem_019_t4](lean_failure_modes_meeting.html#trial=easy_fatem_019_t4&event=0&view=trace), [easy_fatem_019_t8](lean_failure_modes_meeting.html#trial=easy_fatem_019_t8&event=0&view=trace), [easy_fatem_019_t9](lean_failure_modes_meeting.html#trial=easy_fatem_019_t9&event=0&view=trace) |
| Target never attempted | 6 | [easy_fatem_019_t5](lean_failure_modes_meeting.html#trial=easy_fatem_019_t5&event=0&view=trace), [easy_fatem_019_t7](lean_failure_modes_meeting.html#trial=easy_fatem_019_t7&event=0&view=trace), [easy_fatem_020_t3](lean_failure_modes_meeting.html#trial=easy_fatem_020_t3&event=0&view=trace), [easy_fatem_109_t3](lean_failure_modes_meeting.html#trial=easy_fatem_109_t3&event=0&view=trace), [easy_fatem_109_t9](lean_failure_modes_meeting.html#trial=easy_fatem_109_t9&event=0&view=trace), [easy_leancat_002_t1](lean_failure_modes_meeting.html#trial=easy_leancat_002_t1&event=0&view=trace) |

## Medium failures: behavior × controller progress

Each medium trial has two labels: a dominant observed failure behavior and a controller-progress stage. Progress is reconstructed from the subgoal tool ledger and is not a proof-completion percentage.

| Failure behavior | P0 | P1 | P2 | P3 | P4 | P5 | Total |
|---|---:|---:|---:|---:|---:|---:|---:|
| Formalization / interface barrier | 0 | 3 | 1 | 2 | 2 | 0 | 8 |
| Search / recovery loop | 0 | 0 | 0 | 5 | 0 | 0 | 5 |
| Subgoal-scope mismatch | 0 | 0 | 3 | 0 | 1 | 0 | 4 |
| Critic-acceptance mismatch | 0 | 0 | 0 | 0 | 1 | 0 | 1 |
| Handoff without execution | 2 | 0 | 0 | 0 | 0 | 0 | 2 |
| **Total** | **2** | **3** | **4** | **7** | **4** | **0** | **20** |

### Medium trace index

| Trial | Behavior | Stage | Subgoals: defined / attempted / ledger accepted | Replay |
|---|---|---:|---:|---|
| [medium_fateh_001_t0](lean_failure_modes_meeting.html#trial=medium_fateh_001_t0&event=0&view=subgoals) | Formalization / interface barrier | P4 | 5 / 3 / 2 | matched |
| [medium_fateh_001_t1](lean_failure_modes_meeting.html#trial=medium_fateh_001_t1&event=0&view=subgoals) | Formalization / interface barrier | P1 | 4 / 1 / 0 | matched |
| [medium_fateh_001_t2](lean_failure_modes_meeting.html#trial=medium_fateh_001_t2&event=0&view=subgoals) | Formalization / interface barrier | P1 | 4 / 1 / 0 | matched |
| [medium_fateh_001_t3](lean_failure_modes_meeting.html#trial=medium_fateh_001_t3&event=0&view=subgoals) | Formalization / interface barrier | P1 | 4 / 1 / 0 | matched |
| [medium_fateh_001_t4](lean_failure_modes_meeting.html#trial=medium_fateh_001_t4&event=0&view=subgoals) | Subgoal-scope mismatch | P2 | 4 / 1 / 0 | matched |
| [medium_fateh_001_t5](lean_failure_modes_meeting.html#trial=medium_fateh_001_t5&event=0&view=subgoals) | Handoff without execution | P0 | 6 / 0 / 0 | matched |
| [medium_fateh_001_t6](lean_failure_modes_meeting.html#trial=medium_fateh_001_t6&event=0&view=subgoals) | Subgoal-scope mismatch | P2 | 6 / 1 / 0 | matched |
| [medium_fateh_001_t7](lean_failure_modes_meeting.html#trial=medium_fateh_001_t7&event=0&view=subgoals) | Subgoal-scope mismatch | P2 | 4 / 1 / 0 | matched |
| [medium_fateh_001_t8](lean_failure_modes_meeting.html#trial=medium_fateh_001_t8&event=0&view=subgoals) | Formalization / interface barrier | P2 | 5 / 1 / 0 | matched |
| [medium_fateh_001_t9](lean_failure_modes_meeting.html#trial=medium_fateh_001_t9&event=0&view=subgoals) | Handoff without execution | P0 | 5 / 0 / 0 | matched |
| [medium_leancat_008_t0](lean_failure_modes_meeting.html#trial=medium_leancat_008_t0&event=0&view=subgoals) | Formalization / interface barrier | P3 | 4 / 2 / 1 | matched |
| [medium_leancat_008_t1](lean_failure_modes_meeting.html#trial=medium_leancat_008_t1&event=0&view=subgoals) | Search / recovery loop | P3 | 4 / 2 / 1 | matched |
| [medium_leancat_008_t2](lean_failure_modes_meeting.html#trial=medium_leancat_008_t2&event=0&view=subgoals) | Search / recovery loop | P3 | 4 / 1 / 1 | matched |
| [medium_leancat_008_t3](lean_failure_modes_meeting.html#trial=medium_leancat_008_t3&event=0&view=subgoals) | Search / recovery loop | P3 | 4 / 2 / 1 | matched |
| [medium_leancat_008_t4](lean_failure_modes_meeting.html#trial=medium_leancat_008_t4&event=0&view=subgoals) | Formalization / interface barrier | P4 | 5 / 3 / 2 | matched |
| [medium_leancat_008_t5](lean_failure_modes_meeting.html#trial=medium_leancat_008_t5&event=0&view=subgoals) | Critic-acceptance mismatch | P4 | 4 / 3 / 2 | matched |
| [medium_leancat_008_t6](lean_failure_modes_meeting.html#trial=medium_leancat_008_t6&event=0&view=subgoals) | Search / recovery loop | P3 | 4 / 2 / 1 | matched |
| [medium_leancat_008_t7](lean_failure_modes_meeting.html#trial=medium_leancat_008_t7&event=0&view=subgoals) | Subgoal-scope mismatch | P4 | 5 / 3 / 2 | matched |
| [medium_leancat_008_t8](lean_failure_modes_meeting.html#trial=medium_leancat_008_t8&event=0&view=subgoals) | Formalization / interface barrier | P3 | 4 / 2 / 1 | matched |
| [medium_leancat_008_t9](lean_failure_modes_meeting.html#trial=medium_leancat_008_t9&event=0&view=subgoals) | Search / recovery loop | P3 | 4 / 1 / 1 | matched |

“Ledger accepted” means that the recorded controller ledger accepted the subgoal. It does **not** mean independently proved. P5 is reserved for an independently verified final theorem.

## How to verify a statement

1. Follow a trial link into the dashboard.
2. Select the labeled decisive event in **Trace** or the synchronized node in **Role graph**.
3. Inspect **Checks** for candidate kind, statement match, result, and diagnostic.
4. Open **Exact JSONL** for the complete sanitized source record and its causal parents.
5. For medium trials, compare **Subgoals** replay with the recorded terminal ledger and heed any replay-gap warning.

## Provenance and interpretation

- Bundle schema: `meeting-dashboard.bundle.v1`.
- Bundle validation: **passed**; 0 errors and 11 retained warnings.
- Source records, normalized views, and reviewed enrichments are stored as separate layers.
- Recovery uses ordered compiler and exact-target acceptance evidence; it is not inferred from the final outcome label alone.
- Medium behavior is a dominant observed trace pattern, not a complete causal explanation.
- Role-graph edges represent event `caused_by` relations. Subgoal edges represent `depends_on`; the two graphs are not interchangeable.

Registered provenance is embedded in the dashboard (169 relative references). Source-file families:

- `data/batch/` — 62 files
- `data/experiments/qwen_medium_subgoals_v1/` — 21 files
- `docs/lean_easy_failure_report/public/data/` — 1 file

Build and extension details are documented in [`MEETING_DASHBOARD_BUILD.md`](MEETING_DASHBOARD_BUILD.md).
