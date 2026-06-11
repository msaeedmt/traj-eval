"""Routing ledger: turns control-flow decisions into causal edges (O1, Step 2b).

The observer captures *messages*; the speaker-selection function knows *why*
each speaker was chosen. Neither alone can build a causally-meaningful
``caused_by`` edge. The ledger is the small shared object that joins them:

  * the observer reports every event it emits  -> ledger remembers each role's
    latest event_id (``record_emit``);
  * the selector, when it picks the next speaker, records *which event caused
    that choice* (``record_routing``) as a pending cause keyed by the next role;
  * the observer, before stamping the next message's event, asks the ledger for
    that pending cause (``take_pending``) and uses it as ``caused_by``.

This yields routing-derived edges: an event's parent is the event that
triggered the routing decision summoning its author, not merely the event that
happened to precede it in seq order. Those two coincide on a clean linear run
but diverge whenever events interleave or steps branch (e.g. the repair loop),
which is exactly when the causal edge must stay correct.

Step 2b is single-parent: each routing decision records exactly one cause. The
engineer self-edge (a revision also depending on its own prior attempt) is
deferred to the per-step controller, where step-scoped tracking makes it cheap.
"""

from __future__ import annotations

from traj_eval.trace_core.schema import AgentRole


class RoutingLedger:
    """Shared state joining routing decisions to emitted events.

    Not thread-safe; the group chat is single-threaded turn-taking, so a plain
    dict suffices. One ledger instance per trial.
    """

    def __init__(self) -> None:
        # role -> event_id of that role's most recently emitted event
        self._latest: dict[AgentRole, str] = {}
        # role -> pending parent event_ids for that role's *next* event
        self._pending: dict[AgentRole, list[str]] = {}

    def record_emit(self, role: AgentRole, event_id: str) -> None:
        """Observer calls this after writing each event."""
        self._latest[role] = event_id

    def latest_event_id(self, role: AgentRole) -> str | None:
        """Most recent event_id emitted by ``role``, or None if none yet."""
        return self._latest.get(role)

    def record_routing(self, next_role: AgentRole, cause_event_ids: list[str]) -> None:
        """Selector calls this when it picks ``next_role`` to speak.

        ``cause_event_ids`` are the parents to stamp on ``next_role``'s next
        event. None entries are dropped (e.g. a missing 'latest' at trial start).
        """
        self._pending[next_role] = [c for c in cause_event_ids if c is not None]

    def take_pending(self, role: AgentRole) -> list[str]:
        """Observer calls this before stamping ``role``'s next event.

        Returns the pending parents and clears them (each routing decision is
        consumed exactly once). Empty list if nothing pending.
        """
        return self._pending.pop(role, [])
