# traj-eval

Trajectory-level evaluation framework for multi-agent scientific reasoning.

NLP Lab · CAISA Lab · University of Bonn · Summer Semester 2026
Jiadong Han · Mohammad Saeed Motevali Amin

## What this is

Output-centric evaluation cannot say *where* a multi-agent reasoning failure
originates or how it propagates. This public branch applies trajectory
instrumentation to **Lean 4 theorem proving**, where the Lean kernel supplies
an external, step-verifiable verdict. It records inter-agent communication as a
directed event graph, scores both the reasoning process and the final proof,
and attributes anchor violations to specific events and agents.

See `dataset/Lean/README.md` for the benchmark and Lean setup. Model endpoints
use the independent configuration boundary in `src/traj_eval/agents/config.py`;
`configs/qwen.remote.example.env` documents the public Qwen template.

## Quick start

```bash
uv sync --all-extras          # create venv + install everything
uv run pytest                 # run the test suite
uv run python scripts/export_schema.py   # regenerate JSON Schema
```

## Layout

```
src/traj_eval/
  agents/        Lean team, routing, roles, and model boundary
  anchors/lean/  Lean proof-state anchor logic
  dataset/       benchmark loading and verification
  metrics/       communication and Lean outcome metrics
  tools/         Lean compiler and retrieval adapters
  trace_core/    event schema, storage, and graph G              (O1)
dataset/Lean/    public MiniFATELeanCat benchmark and Lake project
schema/          exported JSON Schema
scripts/         Lean batch runner and reproducible analysis
tests/           pytest suite
```

## Objectives (from the proposal)

* **O1** Localisation infrastructure — non-invasive observer, schema-validated
  event log, directed graph, attribution of first anchor violation.
* **O2** Failure taxonomy & automatic detectors over G.
* **O3** Early prediction over Lean proof trajectories (stretch).
