# Provenance: vendored Stargazer subset

Code in this directory is copied **verbatim** from
[AIPS-UofT/Stargazer](https://github.com/AIPS-UofT/Stargazer) and must not be
edited. It is checksum-pinned by `tests/vendor/test_vendor_integrity.py`.

- **Upstream**: https://github.com/AIPS-UofT/Stargazer
- **Commit**: `TODO` — fill in with
  `git -C /path/to/Stargazer rev-parse HEAD`
- **Fetched**: 2026-08-09
- **Licence**: MIT (see `LICENSE`, retained verbatim as the licence requires).
  Benchmark *task data* under `dataset/Astro/` is CC-BY-4.0; see
  `dataset/Astro/PROVENANCE.md`.
- **Paper**: Liu, Zhang, Schölkopf, Jin, Menou. *Stargazer: A Scalable
  Model-Fitting Benchmark Environment for AI Agents under Astrophysical
  Constraints*, arXiv:2604.15664 (2026).

## Files copied

| File | Purpose |
|---|---|
| `config.py` | `Task`, `SystemConfig`, `Observations`, `PlanetParams`, and `Task.from_json` |
| `utils_units.py` | unit conversions and `semi_amplitude_ms` (K from m·sin i, P, e, M★) |
| `forward_keplerian.py` | analytic multi-Keplerian RV forward model |
| `matching.py` | Hungarian truth↔guess planet matching and the distance weights |
| `evaluator.py` | `evaluate_submission`: ΔBIC, RMS, match score, count |

## Modifications

**One**, and it is an omission rather than an edit: `__init__.py` is replaced by
an import-free stub. Upstream's version eagerly imports `task_factory`, `bank`
and `seed_utils`, which require `rebound` (and `celerite2` for GP task
generation). None of that is needed to score a submission, so re-exporting it
would force two heavy dependencies onto every trial and every CI run for no
benefit. Import the modules directly:

```python
from traj_eval.vendor.stargazer.evaluator import evaluate_submission
from traj_eval.vendor.stargazer.config import PlanetParams
```

No other file is altered in any way.

## Why vendor instead of depending on it

Upstream ships no `pyproject.toml` or `setup.py`, so `pip install git+…` does
not work; the alternatives were a git submodule plus a `sys.path` shim, or
copying. Copying wins because:

- it drops `rebound` and `celerite2` entirely (see the `__init__.py` note above);
- no submodule initialisation step to forget on a fresh clone or in CI;
- ordinary imports, so ruff, mypy and editors all resolve the code;
- the copy is immune to an upstream force-push, rename, or deletion.

The one thing a submodule gave us — a guarantee against silent drift — is
recovered by the checksum test, which runs on every CI invocation rather than
only when someone thinks to check `git submodule status`.

## Why reuse this code at all rather than reimplement it

The astro arm's primary baseline is Stargazer's published single-agent results.
That comparison is only meaningful if we grade with the same ruler, and the
grading code is full of choices that are invisible until they bite: Newton
iteration to `1e-12`, eccentricity clipped at `0.95` in the forward model but
`0.999999` in the solver, the phase convention `l_rad = Ω + ω + M₀` measured at
`t_ref = times[0]`, matcher weights `rv_curve=4.0 / dlogP=1.0 / dlogK=0.5 /
de=0.5`, pair rejection above distance `5.0`, and an optimal constant offset
removed before comparing curves. Any single one of those transcribed
differently would still run, still produce plausible numbers, and be quietly
incomparable.

It also matters for the anchors. An anchor asserts *"the agent claimed RMS 1.08,
but it is really 7.71"* — and "really" has to mean what the grader means, or the
measurement becomes the disagreement between two implementations rather than the
agent's error.

## Do not edit

Run `uv run pytest tests/vendor` after any change in this directory. If a
mismatch is intentional (upstream released a fix and you re-vendored on
purpose), update the digests in `test_vendor_integrity.py`, update the commit sha
above, and re-run `scripts/probe_astro_eval.py --all-easy` before trusting any
result.
