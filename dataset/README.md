# Lean Dataset

This folder is a single Lean 4 benchmark project for FATE and LeanCat.

## Layout

- `FATEH/`, `FATEM/`, `FATEX/`: FATE Lean statements.
- `LeanCat/CAT_statement/`: LeanCat Lean statements.
- `LeanCat/problems/`: LeanCat natural-language problem text.
- `LeanCat/records.jsonl`: LeanCat records.
- `lean-toolchain`, `lakefile.lean`, `lake-manifest.json`, `Benchmarks.lean`: shared Lean project files.

## Build

```bash
cd dataset
lake update
lake exe cache get
lake build
```

The Lake cache and build outputs live under `.lake/` and are intentionally not committed.

## Verify Counts

From the repository root:

```bash
uv run python -m traj_eval.dataset.verify
```

Expected counts:

- FATEH: 100 Lean files
- FATEM: 150 Lean files
- FATEX: 100 Lean files
- LeanCat statements: 100 Lean files
- LeanCat records: 100 JSONL rows