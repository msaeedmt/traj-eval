"""Probe how lean-interact surfaces `exact?` / `apply?` suggestions before we
wrap them as a tool. Same discipline as the leansearch and check_lean probes:
run the real thing on known-simple goals and print the RAW response messages
(severity + data) so we see exactly where the `Try this: ...` suggestion lands
and what other messages (errors/warnings) accompany it.

Run: uv run python scripts/probe_exact.py

What we need to learn:
  * Which message carries the suggestion (severity? a `Try this:` prefix?).
  * Whether `exact?` ALSO emits an error/warning we must tolerate.
  * The exact text format so the wrapper can extract the suggested tactic.
"""

from __future__ import annotations

from pathlib import Path

from lean_interact import Command

from traj_eval.tools.lean_compiler import LeanCompiler

PROJECT_DIR = Path.home() / "lean_anchor"

# Goals where exact?/apply? should find a standard-library lemma.
CASES = [
    ("exact? on add_comm", "import Mathlib\nexample (a b : Nat) : a + b = b + a := by\n  exact?"),
    ("apply? on add_comm", "import Mathlib\nexample (a b : Nat) : a + b = b + a := by\n  apply?"),
    ("exact? on le_refl", "import Mathlib\nexample (n : Nat) : n ≤ n := by\n  exact?"),
    (
        "exact? mid-proof (after intro)",
        "import Mathlib\nexample (p q : Prop) (h : p ∧ q) : q := by\n"
        "  obtain ⟨hp, hq⟩ := h\n  exact?",
    ),
]


def main() -> None:
    print(f"Starting compiler against {PROJECT_DIR} (first run slow)...")
    comp = LeanCompiler(PROJECT_DIR)
    server = comp._server  # reuse the same AutoLeanServer
    print("Ready.\n")

    for label, code in CASES:
        print(f"================= {label} =================")
        print(code)
        print("---- raw response messages ----")
        try:
            resp = server.run(Command(cmd=code), timeout=120)
        except Exception as e:  # noqa: BLE001
            print("  RUN ERROR:", type(e).__name__, str(e)[:200])
            print()
            continue
        msgs = getattr(resp, "messages", []) or []
        if not msgs:
            print("  (no messages)")
        for i, m in enumerate(msgs):
            sev = getattr(m, "severity", "?")
            data = getattr(m, "data", "")
            pos = getattr(m, "start_pos", None)
            print(f"  [{i}] severity={sev!r} start_pos={pos}")
            for line in (data or "").splitlines():
                print(f"       | {line}")
        # also show any other useful attributes on the response
        print("  response attrs:", [a for a in dir(resp) if not a.startswith("_")][:12])
        print()


if __name__ == "__main__":
    main()
