# Setup

All development happens inside **WSL2 (Ubuntu)** with the project living in the
Linux filesystem (`~/projects/traj-eval`), edited via Windows VS Code over the
WSL remote. Do **not** work from `/mnt/c/...` — it is slow and breaks file
watching.

## 1. System tools

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y build-essential curl git unzip
```

## 2. uv (Python toolchain)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

## 3. Project deps

```bash
uv sync                 # core only (fast)
uv sync --all-extras    # + agents + dashboard (heavy)
uv run pytest           # verify the core works
```

## 4. Lean 4 + Mathlib (slow — start early, runs in background)

```bash
curl https://elan.lean-lang.org/elan-init.sh -sSf | sh
source $HOME/.elan/env
elan default stable
# Mathlib build happens inside the Lean agent project; expect a long
# compile + several GB. Kick it off before doing anything else.
```

## 5. External repos (smoke-test each unmodified before integrating)

* AG2 / AutoGen [12] — run the 2-agent hello-world.
* CMBAgent [2] — run shipped smoke test.
* minimal Leanagent [13] — solve one FATE problem.
* Stargazer [5] — run forward model, reproduce **one** published single-agent
  result (this is our primary baseline).

## 6. Datasets

Place under `data/` (git-ignored). Run the loaders' count assertions:

```bash
uv run python -m traj_eval.datasets.verify
```

Expected counts: Stargazer 100 synthetic + 20 real (36 easy / 48 medium /
36 hard); [6] 14 CAMB one-shot + 5 deep research; FATE 350; LeanCat 100.
