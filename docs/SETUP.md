# Setup

Everything below was developed and run on Linux (WSL2 Ubuntu). Keep the
project on a Linux filesystem, not under `/mnt/c/...`.

## 1. Python environment

[uv](https://docs.astral.sh/uv/) manages the toolchain and the virtualenv.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

uv sync                 # core only: trace schema, metrics, offline analysis
uv sync --all-extras    # + AG2 agents, lean-interact, streamlit dashboard
uv run pytest           # 311 tests; the core suite needs no API key and no Lean
```

Extras, from `pyproject.toml`:

| extra       | needed for                                        |
|-------------|---------------------------------------------------|
| `agents`    | running trials (AG2 / AutoGen substrate)          |
| `lean`      | the in-loop `check_lean` tool and kernel re-checks |
| `dashboard` | `uv run streamlit run src/traj_eval/dashboard/app.py` |

## 2. Model access

The agents talk to any OpenAI-compatible endpoint. Configuration is by
environment variable only (`src/traj_eval/agents/config.py`); nothing is read
from files inside the repository.

```bash
export OPENAI_API_KEY=...            # required to run trials
export TRAJ_EVAL_MODEL=gpt-4o-mini   # backbone; default gpt-4o-mini
export OPENAI_BASE_URL=...           # optional: self-hosted / gateway endpoint
```

Put these in a `.env` file if you like — it is git-ignored. Offline analysis
of existing traces needs none of them.

## 3. Lean 4 + Mathlib (only for the Lean testbed)

The Lean tools (`check_lean`, `try_tactic`, `show_goals`) and the offline
kernel validator drive a Lean REPL inside a pre-built Mathlib project. Building
Mathlib takes a long time and several GB; start it early.

```bash
curl https://elan.lean-lang.org/elan-init.sh -sSf | sh
source $HOME/.elan/env

# A Lake project that depends on Mathlib. The code expects it at ~/lean_anchor
# (see LeanCompiler in src/traj_eval/tools/lean_compiler.py).
mkdir -p ~/lean_anchor && cd ~/lean_anchor
lake init lean_anchor
# add   [[require]] name = "mathlib" scope = "leanprover-community" rev = "v4.30.0"
# to lakefile.toml, then:
lake exe cache get
lake build
```

The traces in `data/batch` were produced with Lean `v4.30.0` and the matching
Mathlib release (`~/lean_anchor/lean-toolchain`). The `search_lemmas` tool calls
the public LeanSearch API and needs network access.

## 4. Datasets

Both benchmarks are tracked in the repository — nothing to download.

| path                        | contents                                                   |
|-----------------------------|------------------------------------------------------------|
| `dataset/Lean/`             | MiniFATELeanCat: 30 problems (10 easy / 10 medium / 10 hard) drawn from FATE-M/H/X and LeanCat; `metadata.json` is the index |
| `dataset/Astro/synthetic/`  | 100 Stargazer synthetic RV systems (difficulty 1–10)       |
| `dataset/Astro/real/`       | 20 Stargazer archival systems (prepared, never run)        |
| `dataset/Astro/ceilings.json` | per-task maximum-likelihood match ceiling, see `scripts/compute_match_ceilings.py` |

`dataset/Astro/PROVENANCE.md` records the upstream Stargazer commit and the
conversion applied by `scripts/prepare_astro_dataset.py` (a one-time step; it
needs `rebound` and is not part of the normal workflow).

## 5. Running and analysing

See the **Reproduce** section of the top-level `README.md`.
