# traj-eval

Trajectory-level evaluation framework for multi-agent scientific reasoning.

NLP Lab · CAISA Lab · University of Bonn · Summer Semester 2026
Jiadong Han · Mohammad Saeed Motevali Amin

## What this is

Output-centric evaluation cannot say *where* a multi-agent reasoning failure
originates or how it propagates. This framework instruments inter-agent
communication as a directed event graph, scores both the reasoning process and
the final artefact, and attributes anchor violations to specific events and
agents — across two testbeds with contrasting step-checkability:

* **Lean 4** theorem proving (step-verifiable; kernel ground truth)
* **Astrophysical inference** (partially step-verifiable; Stargazer forward model)

See `docs/SETUP.md` for the full environment setup and `docs/ARCHITECTURE.md`
for the module map and the framework-agnostic vs. domain-adaptable split.

## Quick start

```bash
uv sync --all-extras          # create venv + install everything
uv run pytest                 # run the test suite
uv run python scripts/export_schema.py   # regenerate JSON Schema
```

## Layout

```
src/traj_eval/
  trace_core/    framework-agnostic: schema, storage, graph G   (O1)
  anchors/
    lean/        domain-adaptable anchor logic (proof state)
    astro/       domain-adaptable anchor logic (forward model)
  detectors/     trajectory-level failure detectors             (O2)
  experiments/   architecture / backbone / stress matrix        (O3)
  datasets/      loaders + count assertions (FATE, LeanCat, Stargazer)
  dashboard/     trajectory views & anchor inspection (built last)
schema/          exported JSON Schema (generated)
tests/           pytest suite
```

## Objectives (from the proposal)

* **O1** Localisation infrastructure — non-invasive observer, schema-validated
  event log, directed graph, attribution of first anchor violation.
* **O2** Failure taxonomy & automatic detectors over G.
* **O3** Early prediction across verification regimes (stretch).
