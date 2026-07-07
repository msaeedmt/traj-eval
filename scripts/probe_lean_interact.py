"""Probe LeanInteract against the local lean_anchor project (Step 4e groundwork).

Goal: see the EXACT structured response LeanServer.run(Command(...)) returns for
each outcome we care about, in *this* installed version -- not the docs' version.
The Step 4e check_lean() will be built from whatever shapes this prints, the same
way the AG2 probe fixed the observer's tool-message classification.

Run from anywhere (it points at ~/lean_anchor by an absolute path):
    uv run python scripts/probe_lean_interact.py
The FIRST run may take a while (Lean REPL is downloaded/built); later runs are fast.

We test four snippets, one per failure category from our discussion:
  1. clean   -- a real proof: expect no sorries, no error messages.
  2. sorry    -- compiles but unproven: expect a `sorries` entry + a 'sorry' warning.
  3. error    -- does not type-check: expect a severity='error' message.
  4. cheat    -- wrong statement that still compiles (n+0 = n+0): expect CLEAN,
                 which is the whole point -- the compiler CANNOT catch statement
                 weakening; only the offline validator (statement_preserved) can.
We also probe `#print axioms` to confirm we can read the axiom list (category 4
of the 'compiles but wrong' list: added axioms / honesty check).
"""

from __future__ import annotations

import json
from pathlib import Path

from lean_interact import Command, LeanREPLConfig, LeanServer, LocalProject

PROJECT = str(Path.home() / "lean_anchor")

CASES = {
    "clean": "theorem probe_clean (n : Nat) : n + 0 = n := by simp",
    "sorry": "theorem probe_sorry (n : Nat) : n + 0 = n := by sorry",
    "error": "theorem probe_error (n : Nat) : n + 0 = n := by exact 42",
    "cheat": "theorem probe_cheat (n : Nat) : n + 0 = n + 0 := by rfl",
}


def _dump(resp) -> None:
    """Print the response in a way that reveals its real structure."""
    print("  type:", type(resp).__name__)
    # pydantic-style models in lean_interact expose .model_dump(); fall back to vars
    try:
        data = resp.model_dump()
        print("  model_dump:", json.dumps(data, default=str, indent=2)[:1200])
    except Exception:
        print("  repr:", repr(resp)[:1200])
    # the fields we plan to read in check_lean:
    sorries = getattr(resp, "sorries", None)
    messages = getattr(resp, "messages", None)
    print("  -> #sorries:", len(sorries) if sorries is not None else "n/a")
    if sorries:
        for s in sorries:
            print("     sorry.goal:", repr(getattr(s, "goal", None))[:80])
    if messages is not None:
        print("  -> #messages:", len(messages))
        for m in messages:
            print(
                "     msg severity=",
                getattr(m, "severity", None),
                "| data=",
                repr(getattr(m, "data", None))[:80],
            )


def main() -> None:
    print(f"Configuring LeanREPL against project: {PROJECT}")
    config = LeanREPLConfig(project=LocalProject(directory=PROJECT))
    server = LeanServer(config)
    print("Server ready.\n")

    for name, cmd in CASES.items():
        print(f"================= case: {name} =================")
        print("  cmd:", cmd)
        resp = server.run(Command(cmd=cmd))
        _dump(resp)
        print()

    # axiom honesty check: prove cleanly, then ask which axioms it used.
    print("================= case: print_axioms =================")
    server.run(Command(cmd="theorem probe_ax (n : Nat) : n + 0 = n := by simp"))
    resp = server.run(Command(cmd="#print axioms probe_ax"))
    _dump(resp)


if __name__ == "__main__":
    main()
