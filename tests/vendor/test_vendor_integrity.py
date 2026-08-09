"""Pin the vendored Stargazer files as byte-for-byte upstream copies.

This is the guard that replaces a git submodule. A submodule makes drift
mechanically impossible but only if someone remembers to run
``git submodule status``; this checks on every CI run instead, which is
strictly stronger in practice.

The point is not tidiness. Our astro results are compared against Stargazer's
published single-agent baseline, and that comparison is only meaningful if we
graded with the same code. A well-meaning edit here -- reformatting, "fixing" a
lint warning, tightening a tolerance -- would silently invalidate every number
in the report while leaving all other tests green.

If a hash mismatch is intentional (upstream released a fix and you re-vendored
deliberately), update BOTH the digest below AND
``src/traj_eval/vendor/stargazer/PROVENANCE.md``, and re-run
``scripts/probe_astro_eval.py --all-easy`` before trusting any result.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

VENDOR_DIR = Path(__file__).resolve().parents[2] / "src" / "traj_eval" / "vendor" / "stargazer"

# sha256 of each verbatim upstream file, as vendored on 2026-08-09.
EXPECTED_SHA256: dict[str, str] = {
    "config.py": "2e7aa9675d4a5d91177d51cdd0a16c7441da671168aae23771731773761b67c2",
    "utils_units.py": "2d979b4a1d76ee8c6aae18e065d1b913c802285aae689b99cdf1c336ec61162e",
    "forward_keplerian.py": "ecbc43b0205ae87b370db9bb7b4108a33eac2a475b9c13398f3fb52fff93cf31",
    "matching.py": "7a2839fd3e56ab69831ced8973b98cbd8e18129d317d07988bd9d0ce1c3dbc1c",
    "evaluator.py": "8a69ac5d7548a73a14d63a6cadb265bef6dbd0335f746c678a5be63d2bd29de8",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("name", sorted(EXPECTED_SHA256))
def test_vendored_file_is_unmodified(name: str) -> None:
    path = VENDOR_DIR / name
    assert path.is_file(), f"vendored file missing: {path}"
    assert _sha256(path) == EXPECTED_SHA256[name], (
        f"{name} differs from the vendored upstream copy.\n"
        f"These files must stay byte-for-byte identical to AIPS-UofT/Stargazer: "
        f"editing them silently breaks comparability with the published baseline "
        f"while leaving every other test green.\n"
        f"If the change is intentional, update EXPECTED_SHA256 and PROVENANCE.md, "
        f"then re-run scripts/probe_astro_eval.py --all-easy."
    )


def test_no_unexpected_python_files_in_vendor_dir() -> None:
    """Catch files ADDED to the vendor package, which the hash test cannot see."""
    found = {p.name for p in VENDOR_DIR.glob("*.py")} - {"__init__.py"}
    assert found == set(EXPECTED_SHA256), (
        f"vendor directory contents changed.\n"
        f"unexpected: {sorted(found - set(EXPECTED_SHA256))}\n"
        f"missing:    {sorted(set(EXPECTED_SHA256) - found)}"
    )


def test_vendor_init_imports_nothing_from_upstream() -> None:
    """The stub __init__ must contain no import statements at all.

    Upstream's __init__ imports task_factory and bank, which require rebound.
    Re-exporting anything here would drag those back in and defeat the whole
    reason for vendoring a subset. Checked by parsing the AST rather than
    scanning text, so the explanatory docstring cannot trip it.
    """
    source = (VENDOR_DIR / "__init__.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = [node for node in ast.walk(tree) if isinstance(node, ast.Import | ast.ImportFrom)]
    assert not imports, (
        "vendor/stargazer/__init__.py must not import anything: upstream's version "
        "pulls in task_factory and bank, which require rebound. Import the vendored "
        "modules directly instead."
    )
    # Nothing but the module docstring should be present.
    body = [node for node in tree.body if not isinstance(node, ast.Expr)]
    assert not body, "vendor/stargazer/__init__.py should contain only a docstring"


def test_licence_is_present() -> None:
    """MIT requires the copyright notice to travel with the code."""
    licence = VENDOR_DIR / "LICENSE"
    assert licence.is_file(), "upstream LICENSE must be vendored alongside the code"
    text = licence.read_text(encoding="utf-8")
    assert "MIT" in text and "Copyright" in text
