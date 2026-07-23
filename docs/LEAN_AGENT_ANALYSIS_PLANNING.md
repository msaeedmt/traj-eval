# Lean Agent Analysis Planning

## Must-Haves

- Show every failed easy and medium trial with its exact JSONL trace — every failure claim must be independently verifiable.
- Label each selected trace and highlighted event with its reviewed failure mode — the diagnosis must remain visible while navigating evidence.
- Keep the interactive role-swimlane graph synchronized with trace, checks, subgoals, and JSON views — one selected event should reconcile everywhere.
- Show all 20 medium trials with dominant behavior, P0–P5 progress, subgoal DAG, and event-time status — partial progress must not be confused with proof completion.
- Include all 17 recovery successes plus the `easy_fatem_011_t0` one-shot contrast — recovery claims need complete compiler-to-acceptance evidence.
- Provide a reproducible shell command for every failed trial — reviewers should be able to rerun the exact experiment quickly.
- Keep adapters, enrichments, taxonomy, and UI capabilities modular — future experiments should not require experiment-name-specific dashboard code.

## Bugs & Ideas

- Persist failed probes as structured negative evidence — chat history alone did not stop the engineer from retrying rejected lemma names.
- Count probes separately from submitted attempts — `medium_fateh_001_t0` made many compiler calls while the ledger reported only one failed attempt.
- Treat `compiled=true` with `sorry_free=false` as an incomplete probe — dashboards must never display placeholder-backed compilation as proof progress.
- Detect repeated normalized probes and previously rejected identifiers — repeated API guesses are an early-warning signature for recovery loops.
- Escalate prolonged probe loops to the reasoner or critic — the current critic cannot intervene before the engineer submits a candidate.
- Validate planner dependencies for logical sufficiency — an upper bound alone cannot establish a nonzero subgroup index.
- Distinguish terminal mechanism from causal failure mode — `turn cap` explains stopping, not why the agent became stuck.

## Fun

- Add side-by-side failed-versus-recovered trace comparison — contrasting event paths may reveal which repair behaviors actually work.
- Add a compact negative-memory panel per subgoal — reviewers could see known-bad lemmas, repeated probes, and unused compiler evidence at a glance.
- Add one-click copyable meeting references for trial, event, mode, and source line — discussion can jump directly to the same evidence.
- Add replay animation for role graph and subgoal state — temporal progression would be easier to present than a static final graph.
- Add cross-experiment failure-pattern similarity search — future traces could be compared with previously diagnosed agent behaviors.
