"""ONE-TIME preparation: convert upstream Stargazer tasks into our dataset.

Run this once, then commit ``dataset/Astro/``. After that no trial, test, or CI
job ever needs ``rebound`` or an upstream checkout again.

What it does and why
--------------------
Upstream applies ``bank._apply_rv_only_compat`` on every single task load. That
conversion (a) replaces the REBOUND N-body RV signal with the analytic
multi-Keplerian signal for the same planets, preserving the original noise
realisation, and (b) rewrites the angle convention to RV-only semantics
(``l_rad -= Omega_rad``, then ``Omega_rad = 0``). It is not optional
preprocessing: the evaluator's forward model only understands the analytic form,
so without it the ground truth itself would not score match 1.0.

Because the conversion is deterministic and needs an N-body integration only to
reconstruct the signal it is about to discard, doing it once offline is exactly
equivalent to upstream doing it at load time -- and it removes ``rebound`` and
``celerite2`` from our dependency set entirely.

This is the only file in the project permitted to touch ``sys.path`` or import
upstream directly, because it is a one-off tool, not part of the trial path.

Note on real_004 (GJ 876): a Laplace resonance chain where Keplerian
superposition is genuinely invalid. Upstream converts it anyway (its own runner
applies the same compat step), so we match that behaviour rather than special-
casing it -- the paper keeps the task deliberately, to test whether agents
notice that the model family is misspecified.

Usage
-----
    git clone https://github.com/AIPS-UofT/Stargazer /tmp/Stargazer
    uv run --with rebound --with celerite2 python scripts/prepare_astro_dataset.py \
        --stargazer-root /tmp/Stargazer

    # verify without writing:
    uv run --with rebound python scripts/prepare_astro_dataset.py \
        --stargazer-root /tmp/Stargazer --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from traj_eval.dataset.astro_bank import ACCEPTED_RV_SEMANTICS, bank_dir

# Upstream bank subdirectories, keyed by our own 'kind' label.
UPSTREAM_BANKS = {
    "synthetic": Path("stargazer") / "Stargazer_synthetic_task",
    "real": Path("stargazer") / "Stargazer_real_data_task",
}


def _add_upstream_to_path(root: Path) -> None:
    """Make ``import stargazer`` resolve against the upstream checkout.

    Upstream's ``stargazer/__init__.py`` eagerly imports ``task_factory`` and
    ``bank``, which require ``rebound`` (and ``celerite2`` for GP generation) --
    which is precisely why the runtime code vendors five modules instead of
    depending on the package. Here we DO want the full package, because
    ``_apply_rv_only_compat`` needs ``engine_rebound.simulate_clean_rv``.
    """
    pkg = root / "stargazer"
    if not pkg.is_dir():
        raise SystemExit(f"No 'stargazer' package under {root}. Is --stargazer-root correct?")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def prepare_bank(
    root: Path,
    kind: str,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> Counter:
    """Convert every task in one upstream bank; return a status tally."""
    from stargazer.bank import TaskBank  # noqa: PLC0415 - after sys.path setup

    src_dir = root / UPSTREAM_BANKS[kind]
    if not src_dir.is_dir():
        raise SystemExit(f"Upstream bank not found: {src_dir}")
    dst_dir = bank_dir(kind)
    if not dry_run:
        dst_dir.mkdir(parents=True, exist_ok=True)

    # TaskBank.load_task applies _apply_rv_only_compat for us.
    bank = TaskBank(str(src_dir))
    task_ids = bank.list_tasks()
    tally: Counter = Counter()
    print(f"\n[{kind}] {len(task_ids)} task(s) in {src_dir}")

    for task_id in task_ids:
        dst = dst_dir / f"{task_id}.json"
        if dst.exists() and not force:
            tally["skipped_exists"] += 1
            continue

        task = bank.load_task(task_id)
        semantics = (task.meta or {}).get("rv_semantics")
        if semantics not in ACCEPTED_RV_SEMANTICS:
            # The conversion ran but did not mark the task -- possible if
            # simulate_clean_rv raised and _apply_rv_only_compat silently
            # returned the task unchanged (it catches broad Exception). Refuse
            # to write it rather than commit a file that will mis-score.
            tally["FAILED_unconverted"] += 1
            print(f"  !! {task_id}: rv_semantics={semantics!r} after load -- NOT written")
            continue

        tally[f"ok_{semantics}"] += 1
        if not dry_run:
            dst.write_text(task.to_json(), encoding="utf-8")

    return tally


def write_provenance(root: Path, tallies: dict[str, Counter], *, commit: str | None) -> None:
    """Record where the data came from and what was done to it."""
    lines = [
        "# Astro dataset provenance",
        "",
        "Task files converted from AIPS-UofT/Stargazer by",
        "`scripts/prepare_astro_dataset.py`.",
        "",
        f"- upstream checkout: `{root}`",
        f"- upstream commit: `{commit or 'TODO: fill in (git -C <checkout> rev-parse HEAD)'}`",
        "- conversion applied: `bank._apply_rv_only_compat`",
        "  (REBOUND signal replaced by analytic multi-Keplerian, noise realisation",
        "  preserved; `l_rad -= Omega_rad`, `Omega_rad = 0`)",
        "- task data licence: CC-BY-4.0 (code is MIT; see",
        "  `src/traj_eval/vendor/stargazer/LICENSE`)",
        "",
        "This is exactly the conversion upstream performs at load time in both",
        "`TaskBank.load_task` and `RvEnv.reset`, so scoring stays comparable to the",
        "published baseline. Baking it in removes `rebound` and `celerite2` from the",
        "runtime dependency set.",
        "",
        "## Counts",
        "",
    ]
    for kind, tally in tallies.items():
        lines.append(f"- **{kind}**: " + ", ".join(f"{k}={v}" for k, v in sorted(tally.items())))
    lines.append("")
    path = bank_dir("synthetic").parent / "PROVENANCE.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwrote {path}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stargazer-root", required=True, type=Path, help="upstream checkout")
    ap.add_argument(
        "--kinds", nargs="+", default=["synthetic", "real"], choices=["synthetic", "real"]
    )
    ap.add_argument("--dry-run", action="store_true", help="convert and report, write nothing")
    ap.add_argument("--force", action="store_true", help="overwrite already-prepared files")
    ap.add_argument("--commit", default=None, help="upstream commit sha, for PROVENANCE.md")
    args = ap.parse_args(argv)

    root = args.stargazer_root.expanduser().resolve()
    _add_upstream_to_path(root)

    tallies: dict[str, Counter] = {}
    for kind in args.kinds:
        tallies[kind] = prepare_bank(root, kind, dry_run=args.dry_run, force=args.force)

    print("\n" + "=" * 64)
    failed = 0
    for kind, tally in tallies.items():
        print(f"[{kind}] " + json.dumps(dict(sorted(tally.items()))))
        failed += tally.get("FAILED_unconverted", 0)

    if args.dry_run:
        print("\nDRY RUN -- nothing written.")
        return 1 if failed else 0

    write_provenance(root, tallies, commit=args.commit)
    if failed:
        print(f"\n{failed} task(s) could not be converted. Fix before running trials.")
        return 1
    print("\nDataset prepared. Commit dataset/Astro/, then run scripts/probe_astro_eval.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
