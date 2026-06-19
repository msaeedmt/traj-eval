# Mini FATE + LeanCat Benchmark

This is a compact Lean 4 / Mathlib benchmark for trajectory evaluation.
It contains 30 theorem-proving tasks:

- Easy: 2 LeanCat Easy + 8 FATE-M
- Medium: 2 LeanCat Medium + 8 FATE-H
- Hard: 2 LeanCat High + 8 FATE-X

The old large benchmark corpus is kept private in the local checkout. The
public dataset surface is the `MiniFATELeanCat` library and `metadata.json`.

## Layout

- `MiniFATELeanCat/Easy/`: 10 easy tasks.
- `MiniFATELeanCat/Medium/`: 10 medium tasks.
- `MiniFATELeanCat/Hard/`: 10 hard tasks.
- `Benchmarks.lean`: package-level benchmark entrypoint; imports all 30 task files.
- `metadata.json`: source, difficulty, and import metadata.

Each task imports focused Mathlib modules instead of `import Mathlib`.

## Build

```bash
cd dataset
lake update
lake exe cache get
lake build
```
