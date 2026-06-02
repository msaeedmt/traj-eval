"""Trial log storage: JSON Lines, one file per trial.

Simplest thing that works, human-inspectable, git-diffable. The TrialLog
interface is deliberately narrow so a future SQLite/Parquet backend can drop
in without touching observer or detector code.

File format (one JSON object per line):
    line 0    : TrialMeta
    line 1..n : TraceEvent (in seq order)
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import orjson

from traj_eval.trace_core.schema import TraceEvent, TrialMeta


class TrialLogWriter:
    """Append-only writer for a single trial."""

    def __init__(self, path: str | Path, meta: TrialMeta):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("wb")
        self._write(meta.model_dump(mode="json"))

    def _write(self, obj: dict) -> None:
        self._fh.write(orjson.dumps(obj))
        self._fh.write(b"\n")

    def append(self, event: TraceEvent) -> None:
        self._write(event.model_dump(mode="json"))

    def close(self) -> None:
        self._fh.close()

    def __enter__(self) -> TrialLogWriter:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def read_trial(path: str | Path) -> tuple[TrialMeta, list[TraceEvent]]:
    """Load a trial log, validating every record against the schema."""
    lines = Path(path).read_bytes().splitlines()
    if not lines:
        raise ValueError(f"Empty trial log: {path}")
    meta = TrialMeta.model_validate(orjson.loads(lines[0]))
    events = [TraceEvent.model_validate(orjson.loads(ln)) for ln in lines[1:]]
    events.sort(key=lambda e: e.seq)
    return meta, events


def iter_events(path: str | Path) -> Iterator[TraceEvent]:
    """Stream events without holding the whole trial in memory."""
    with Path(path).open("rb") as fh:
        next(fh, None)  # skip meta line
        for ln in fh:
            if ln.strip():
                yield TraceEvent.model_validate(orjson.loads(ln))
