"""AG2-based agent substrate.

Two domain teams (``lean_team``, ``astro_team``) are instantiations of one
free-routing controller (``free_routing``): each role chooses its own next
action via a marker line or a native tool call, and the controller validates
the choice against the domain's allowed-move graph and records how the run
ended. The non-invasive observer (``observer``) turns every message, tool call
and result into a schema-valid trace event; the routing ledger (``routing``)
turns routing decisions into causal edges.

This package does not depend on ``trace_core`` except to reuse the canonical
role names.
"""

from traj_eval.agents.config import build_llm_config
from traj_eval.agents.observer import StepContext, TraceObserver, make_trial_meta
from traj_eval.agents.routing import RoutingLedger

__all__ = [
    "RoutingLedger",
    "StepContext",
    "TraceObserver",
    "build_llm_config",
    "make_trial_meta",
]
