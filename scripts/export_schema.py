"""Export the trace event schema as JSON Schema.

Run after any schema change so non-Python tooling (e.g. Lean-side validation)
checks against the identical contract:

    uv run python scripts/export_schema.py
"""

from __future__ import annotations

import json
from pathlib import Path

from traj_eval.trace_core.schema import SCHEMA_VERSION, TraceEvent, TrialMeta

OUT = Path(__file__).resolve().parent.parent / "schema"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    (OUT / "trace_event.schema.json").write_text(
        json.dumps(TraceEvent.model_json_schema(), indent=2)
    )
    (OUT / "trial_meta.schema.json").write_text(json.dumps(TrialMeta.model_json_schema(), indent=2))
    print(f"Exported JSON Schema v{SCHEMA_VERSION} to {OUT}")


if __name__ == "__main__":
    main()
