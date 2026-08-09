"""Vendored subset of AIPS-UofT/Stargazer. Intentionally EMPTY of imports.

Upstream's own ``__init__.py`` eagerly imports ``task_factory``, ``bank`` and
``seed_utils``, which pull in ``rebound`` (and ``celerite2`` for GP task
generation). None of that is needed to SCORE a submission, so re-exporting it
here would force two heavy dependencies on every trial and every CI run for no
benefit. Import the modules directly instead:

    from traj_eval.vendor.stargazer.evaluator import evaluate_submission
    from traj_eval.vendor.stargazer.config import PlanetParams

Files in this package are byte-for-byte upstream and checksum-pinned. See
PROVENANCE.md.
"""
