"""Build the directed interaction graph G and walk it in causal order (O1).

G has events as nodes and `caused_by` relations as edges. Error localisation
walks G in causal order and records the first event whose anchor is violated.
"""

from __future__ import annotations

import networkx as nx

from traj_eval.trace_core.schema import AnchorStatus, TraceEvent


def build_graph(events: list[TraceEvent]) -> nx.DiGraph:
    """Construct G. Nodes carry the full TraceEvent as `event` attribute."""
    g = nx.DiGraph()
    for ev in events:
        g.add_node(ev.event_id, event=ev)
    for ev in events:
        for parent in ev.caused_by:
            if parent in g:
                g.add_edge(parent, ev.event_id)
    return g


def causal_order(events: list[TraceEvent]) -> list[TraceEvent]:
    """Topological order, falling back to `seq` for ties / missing edges.

    A clean topological sort requires G to be a DAG. If the trajectory has
    cycles (which detectors *want* to find), we sort by seq instead so the
    walk still terminates.
    """
    g = build_graph(events)
    if nx.is_directed_acyclic_graph(g):
        order = list(nx.topological_sort(g))
        by_id = {e.event_id: e for e in events}
        return [by_id[n] for n in order]
    return sorted(events, key=lambda e: e.seq)


def first_violation(events: list[TraceEvent]) -> TraceEvent | None:
    """First event in causal order whose anchor is a violation (O1 core)."""
    for ev in causal_order(events):
        if ev.anchor is not None and ev.anchor.status == AnchorStatus.VIOLATION:
            return ev
    return None
