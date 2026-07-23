# Building the Lean meeting dashboard

This directory contains a focused, offline dashboard and a Markdown companion report for reviewing Lean agent failure and recovery traces in a teammate meeting. Both artifacts are generated from the same validated experiment bundle; neither report is an independent source of truth.

The build is intentionally separate from the broad exploratory report in this directory. It does not modify raw trajectories, the broad dashboard, or the Vibe Coding prototype used as a visual reference.

## Deliverables

- `lean_failure_modes_meeting.html` — self-contained interactive dashboard. It contains the compiled UI, styles, validated bundle, provenance, and a semantic fallback. It makes no network requests.
- `lean_failure_modes_meeting.md` — focused, shareable report generated from the same bundle.

The current meeting bundle contains exactly:

| Cohort | Complete traces |
|---|---:|
| Easy failures | 44 |
| Medium failures with subgoal tools | 20 |
| Recovery successes | 17 |
| One-shot contrast (`easy_fatem_011_t0`) | 1 |
| **Total** | **82** |

Those traces contain 4,430 normalized events and 4,311 causal edges. The build fails if the verified scope changes without an intentional registry or taxonomy update.

## Commands

Run commands from `docs/lean_easy_failure_report`:

~~~powershell
npm.cmd run build:meeting
npm.cmd run check:meeting
npm.cmd run test:meeting
~~~

- `build:meeting` builds in memory and writes the two meeting artifacts only after validation succeeds.
- `check:meeting` performs the same build in memory, then checks that the committed HTML and Markdown are byte-for-byte current. It does not invoke the broad report's mutating data-sync build.
- `test:meeting` exercises the bundle, classifications, progress replay, sanitization, offline HTML, and hash-linked trace navigation.

The HTML build uses Vite programmatically with `write: false`. The resulting JavaScript and CSS are embedded into a single file together with the data bundle. This avoids a temporary distributable directory and keeps the artifact usable from `file://` in a meeting room without a server.

## Source and enrichment boundary

The dashboard distinguishes three evidence layers:

1. **Source records** — the exact canonical JSONL header and event records, with only documented privacy/path sanitization.
2. **Normalized views** — event, check, and causal-edge projections derived deterministically from those records.
3. **Reviewed enrichments** — failure classifications, recovery markers, progress stages, annotations, and manual taxonomy assignments with event-level evidence references.

A diagnosis is never written back into a raw record. A replayed subgoal state is never presented as a source-recorded state. The UI displays workflow verdicts and Lean/kernel verdicts separately.

### Canonical bundle contract

`buildMeetingExperimentBundle` returns a versioned, experiment-independent object with this top-level shape:

~~~text
{
  schemaVersion,
  generatedAt,
  scope,
  experiments[],
  trials[],
  taxonomies,
  metricDefinitions,
  views,
  provenance,
  validation
}
~~~

Every trial uses the same base contract:

~~~text
{
  trialId, experimentId, taskId, trialNumber,
  source, difficulty, sectionId, groupId, metadata, outcome,
  classifications, summary,
  rawRecords[], events[], checks[], graph,
  annotations[], extensions, provenance
}
~~~

Important invariants:

- `rawRecords` retains the source-faithful sanitized JSONL header and all events in source order.
- `events` contains normalized event records with stable raw sequence numbers.
- `graph` contains only trajectory causality (`caused_by`) edges.
- `checks` pairs Lean tool calls and responses by tool-call ID and records unmatched calls or results explicitly.
- `classifications` contains reviewed labels; it does not mutate `events` or `rawRecords`.
- Optional capabilities live under `extensions`. Medium trials currently declare `extensions.subgoals`.
- UI modules branch on declared data capabilities, not experiment names.

### Optional subgoal extension

The medium-trial adapter exposes:

~~~text
extensions.subgoals = {
  nodes[],
  frames[],
  transitions[],
  replayValidation
}
~~~

- `nodes` contains the recorded subgoal definitions and `depends_on` relationships.
- `frames` is the event-time ledger state history.
- `transitions` captures definitions, compiler outcomes, reviews, revisions, recoveries, and ledger changes.
- `replayValidation` compares reconstructed terminal state with the recorded final state. Any disagreement is a visible replay-gap warning, not silently repaired.

The subgoal DAG is distinct from the role-swimlane causal graph. The former uses `depends_on`; the latter uses event `caused_by` links.

## Experiment registry and adapters

`config/meeting-experiments.mjs` is the only place where an experiment enters the meeting bundle. A registry entry declares source paths, adapter, capabilities, cohort selection, and enricher chain.

To add another canonical trajectory experiment:

1. Add one registry entry with a stable experiment ID and source glob.
2. Reuse the generic JSONL adapter when the source follows the canonical header/event schema.
3. Add a new adapter only when the source format differs. Keep source parsing separate from review labels.
4. Add any optional enrichment as a capability-producing module.
5. Add or update versioned taxonomy assignments with exact evidence references.
6. Extend the expected scope intentionally and update the tests.
7. Run `test:meeting`, `build:meeting`, then `check:meeting`.

An adapter should reject malformed headers, duplicate trial IDs, duplicate event sequence numbers, dangling causal parents, and source-trace mismatches. It must preserve complete records rather than retaining only fields needed by the current UI.

## Enrichers

The build currently composes four focused stages:

- **Generic JSONL adapter** — parses canonical trajectory JSONL, normalizes events, and constructs causal edges.
- **Easy analysis enricher** — joins reviewed diagnosis and kernel evidence to easy trials.
- **Taxonomy/recovery enricher** — attaches versioned failure-mode assignments and applies the terminal-acceptance recovery rule.
- **Medium subgoal enricher** — parses response snapshots, pairs tool calls/results, reconstructs the subgoal ledger, and assigns observed behavior plus P0–P5 progress.

Medium execution-result `content` fields are Python literal representations, not JSON. `extract-subgoal-states.py` parses only literals using Python's standard-library `ast.literal_eval`; it does not evaluate code and does not create temporary files.

## Metric definitions

### Recovery success

A recovery success is a kernel-confirmed exact-target run where at least one failed compiler result occurs before the **terminal selected exact-target acceptance**. A run may compile earlier, regress, and recover later. `easy_fatem_012_t1` is the regression sentinel and must show:

~~~text
early pass -> failed compiler result(s) -> terminal exact-target acceptance
~~~

The dashboard exposes all 17 qualifying traces. Recovery counts are based on event ordering, exact-statement matching, and the terminal selected acceptance; they are not inferred from a final success label alone.

### One-shot success

A one-shot success is a solved easy trial that does not satisfy the recovery rule. The dashboard indexes all 39 such trials and embeds `easy_fatem_011_t0` as the complete contrast trace. Indexed-only one-shot trials are not included in the 82 complete-trace scope.

### Easy failure modes

The 44 easy failures are a reviewed partition, not an automatically discovered ontology:

| Reviewed mode | Count |
|---|---:|
| Statement drift / false acceptance | 5 |
| Opaque verifier feedback | 15 |
| Application / type mismatch | 7 |
| Typeclass resolution | 6 |
| Unknown Mathlib symbol / API | 5 |
| Target never attempted | 6 |

Assignments are versioned configuration and include raw event evidence. The counts must sum to 44.

### Medium failure behavior

Each medium trial has one dominant **observed failure behavior**. This is a presentation classification of the trace, not a claim about a latent model defect.

| Failure behavior | P0 | P1 | P2 | P3 | P4 | P5 | Total |
|---|---:|---:|---:|---:|---:|---:|---:|
| Formalization/interface barrier | 0 | 3 | 1 | 2 | 2 | 0 | 8 |
| Search/recovery loop | 0 | 0 | 0 | 5 | 0 | 0 | 5 |
| Subgoal-scope mismatch | 0 | 0 | 3 | 0 | 1 | 0 | 4 |
| Critic-acceptance mismatch | 0 | 0 | 0 | 0 | 1 | 0 | 1 |
| Handoff without execution | 2 | 0 | 0 | 0 | 0 | 0 | 2 |

### Controller-progress stages

Progress measures observable controller workflow, not mathematical proof completion:

- `P0` — planned only.
- `P1` — compiler engaged; no `review_subgoal` decision.
- `P2` — critic reached; no subgoal ledger-accepted.
- `P3` — exactly one subgoal ledger-accepted.
- `P4` — at least two subgoals ledger-accepted.
- `P5` — final theorem independently verified.

Current stage totals are `2 / 3 / 4 / 7 / 4 / 0` for P0 through P5. “Ledger accepted” means only that the recorded controller ledger accepted a subgoal. It is never relabeled “proved” and is never converted to a proof-completion percentage.

## Sanitization and privacy

Sanitization occurs while constructing source-faithful records and is validated again on the final HTML:

- remove private absolute Windows and POSIX workspace paths;
- remove temporary Lean filenames while retaining the diagnostic content needed for review;
- preserve trial IDs, raw sequence numbers, Lean code, tool payloads, compiler messages, anchors, and causal parents;
- avoid embedding environment variables, credentials, browser state, or unrelated local data;
- escape data before embedding so JSON cannot terminate its containing `<script>` element.

The tests scan both the serialized bundle and final HTML for private absolute paths, temporary Lean filenames, external scripts/styles/fonts, and network-capable URLs. Sanitization must not change event counts or ordering.

## UI architecture

The dashboard follows an evidence tree rather than placing every trace on screen:

~~~text
Failure/success pattern -> task/trial -> trace -> event
~~~

Only the selected trace is rendered. The same browser module powers recovery, easy-failure, medium-failure, and one-shot contrast views. The views are synchronized by:

~~~text
#trial=<trial-id>&event=<raw-seq>&view=<trace|graph|checks|json|subgoals>
~~~

An invalid hash falls back visibly to a valid trial, event, and view. “Copy trace reference” copies a filename-relative reference plus trial ID and selected sequence so a teammate can reopen the same evidence without a server.

The HTML also includes a semantic no-script and print fallback containing the definitions, cohort totals, easy-mode partition, medium matrix, and trace index.

## Prototype decisions

The existing broad dashboard and the Vibe Coding prototype are references only.

Adopted:

- numbered role-swimlane graph and exact event/graph synchronization;
- clear `caused_by` edge semantics;
- offline data embedding;
- evidence-order navigation and progressive disclosure;
- separate workflow and kernel verdicts;
- collapsed exact JSON;
- previous/next navigation and accessible controls.

Rejected for this meeting surface:

- large instructional introductions and mathematical lessons;
- repeated KPI grids and 17 simultaneous recovery cards;
- judgment exercises, localStorage, and presentation-sprint content;
- decorative gradients, large hero panels, excessive badges, and duplicated explanations.

The visual system uses a warm near-white background, dark ink, hairline dividers, one principal surface, restrained semantic colors, system fonts, and a 16/24 px spacing rhythm. Color is always paired with text or an icon.

## Release checklist

Before sharing the artifact:

1. Run `npm.cmd run test:meeting`.
2. Run `npm.cmd run build:meeting`.
3. Run `npm.cmd run check:meeting`.
4. Open the HTML through `file://` with network disabled.
5. Confirm recovery selection, event synchronization, matrix filtering, subgoal replay warnings, invalid-hash fallback, keyboard operation, mobile drawer, print view, and no-script fallback.
6. Search the generated files for private absolute paths and temporary Lean filenames.
7. Confirm the artifact counts: 82 traces, 4,430 events, 4,311 causal edges.

The meeting artifacts are reproducible views of the registered evidence. If a raw trace or reviewed assignment changes, rebuild and review the generated diff rather than editing the HTML or Markdown by hand.
