"""Bounded trial-local subgoal state and verifier-backed AG2 tools."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SubgoalStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    CANDIDATE = "candidate"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    BLOCKED = "blocked"


@dataclass
class SubgoalNode:
    id: str
    objective: str
    depends_on: tuple[str, ...]
    status: SubgoalStatus = SubgoalStatus.PENDING
    attempts: int = 0
    consecutive_failures: int = 0
    candidate_hash: str | None = None
    accepted_hash: str | None = None
    engineer_verified: set[str] = field(default_factory=set)
    critic_verified: set[str] = field(default_factory=set)
    failures: list[str] = field(default_factory=list)
    feedback: str = ""


class SubgoalLedger:
    """A small dependency graph whose accepted nodes require critic evidence."""

    _ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")

    def __init__(
        self,
        *,
        max_nodes: int = 6,
        max_failures: int = 3,
        max_forced_replans: int = 2,
        max_failure_notes: int = 3,
    ) -> None:
        self.max_nodes = max_nodes
        self.max_failures = max_failures
        self.max_forced_replans = max_forced_replans
        self.max_failure_notes = max_failure_notes
        self.nodes: dict[str, SubgoalNode] = {}
        self.version = 0
        self.forced_recoveries = 0
        self.strategy_revisions = 0

    @property
    def active_id(self) -> str | None:
        for node in self.nodes.values():
            if node.status is SubgoalStatus.ACTIVE:
                return node.id
        return None

    @property
    def plan_ready(self) -> bool:
        leaves = [node for node in self.nodes.values() if not node.depends_on]
        integrations = [node for node in self.nodes.values() if node.depends_on]
        return len(self.nodes) >= 3 and len(leaves) >= 2 and bool(integrations)

    def _error(self, message: str) -> dict[str, Any]:
        return {"ok": False, "error": message, "state": self.snapshot()}

    def _trim(self, text: str, limit: int = 500) -> str:
        return " ".join((text or "").split())[:limit]

    def _activate_ready(self) -> None:
        if self.active_id is not None:
            return
        accepted = {
            node.id for node in self.nodes.values() if node.status is SubgoalStatus.ACCEPTED
        }
        for node in self.nodes.values():
            if node.status in {SubgoalStatus.PENDING, SubgoalStatus.REJECTED} and set(
                node.depends_on
            ) <= accepted:
                node.status = SubgoalStatus.ACTIVE
                return

    def _would_create_cycle(self, subgoal_id: str, dependencies: tuple[str, ...]) -> bool:
        frontier = list(dependencies)
        visited: set[str] = set()
        while frontier:
            item = frontier.pop()
            if item == subgoal_id:
                return True
            if item in visited:
                continue
            visited.add(item)
            frontier.extend(self.nodes[item].depends_on)
        return False

    def plan_subgoal(
        self, subgoal_id: str, objective: str, depends_on: list[str]
    ) -> dict[str, Any]:
        subgoal_id = subgoal_id.strip()
        objective = self._trim(objective)
        dependencies = tuple(dict.fromkeys(item.strip() for item in depends_on if item.strip()))
        if not self._ID_RE.fullmatch(subgoal_id):
            return self._error("subgoal_id must be a short ASCII identifier")
        if not objective:
            return self._error("objective is required")
        if subgoal_id in dependencies:
            return self._error("a subgoal cannot depend on itself")
        missing = [item for item in dependencies if item not in self.nodes]
        if missing:
            return self._error(f"dependencies must already exist: {missing}")
        if self._would_create_cycle(subgoal_id, dependencies):
            return self._error("dependencies must remain acyclic")

        node = self.nodes.get(subgoal_id)
        created = node is None
        revised = False
        if node is None:
            if len(self.nodes) >= self.max_nodes:
                return self._error(f"subgoal limit reached ({self.max_nodes})")
            node = SubgoalNode(subgoal_id, objective, dependencies)
            self.nodes[subgoal_id] = node
        else:
            if node.status in {SubgoalStatus.ACCEPTED, SubgoalStatus.CANDIDATE}:
                return self._error("accepted or submitted subgoals cannot be revised")
            revised = node.objective != objective or node.depends_on != dependencies
            if not revised:
                if node.status is SubgoalStatus.BLOCKED:
                    return self._error("a blocked subgoal requires a genuine strategy revision")
                return {
                    "ok": True,
                    "created": False,
                    "revised": False,
                    "subgoal_id": subgoal_id,
                    "state": self.snapshot(),
                }
            node.objective = objective
            node.depends_on = dependencies
            node.status = SubgoalStatus.PENDING
            node.consecutive_failures = 0
            node.candidate_hash = None
            node.accepted_hash = None
            node.engineer_verified.clear()
            node.critic_verified.clear()
            self.strategy_revisions += 1

        self.version += 1
        self._activate_ready()
        return {
            "ok": True,
            "created": created,
            "revised": revised,
            "subgoal_id": subgoal_id,
            "state": self.snapshot(),
        }

    def record_compile(
        self,
        *,
        code: str,
        subgoal_id: str,
        purpose: str,
        compiled: bool,
        summary: str,
        reviewer: bool,
    ) -> dict[str, Any]:
        code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
        node = self.nodes.get(subgoal_id)
        if node is None:
            return {"ok": False, "error": "unknown subgoal", "evidence_hash": code_hash}

        if reviewer:
            if node.status is not SubgoalStatus.CANDIDATE:
                return {
                    "ok": False,
                    "error": "critic may review only a submitted candidate",
                    "evidence_hash": code_hash,
                }
            if compiled:
                node.critic_verified.add(code_hash)
            return {"ok": True, "evidence_hash": code_hash}

        if node.status is not SubgoalStatus.ACTIVE:
            return {
                "ok": False,
                "error": "engineer may compile only the active subgoal",
                "evidence_hash": code_hash,
            }

        recovery_required = False
        recovery_exhausted = False
        if purpose in {"subgoal", "final"}:
            node.attempts += 1
            if compiled:
                node.engineer_verified.add(code_hash)
                node.consecutive_failures = 0
            else:
                node.consecutive_failures += 1
                node.failures.append(self._trim(summary, 300))
                node.failures = node.failures[-self.max_failure_notes :]
                if node.consecutive_failures >= self.max_failures:
                    node.status = SubgoalStatus.BLOCKED
                    if self.forced_recoveries < self.max_forced_replans:
                        self.forced_recoveries += 1
                        recovery_required = True
                    else:
                        recovery_exhausted = True
            self.version += 1

        return {
            "ok": True,
            "evidence_hash": code_hash,
            "recovery_required": recovery_required,
            "recovery_exhausted": recovery_exhausted,
        }

    def submit_subgoal(
        self, subgoal_id: str, evidence_hash: str, summary: str
    ) -> dict[str, Any]:
        node = self.nodes.get(subgoal_id)
        if node is None:
            return self._error("unknown subgoal")
        if node.status is not SubgoalStatus.ACTIVE:
            return self._error("only the active subgoal may be submitted")
        if evidence_hash not in node.engineer_verified:
            return self._error("submission lacks successful engineer compiler evidence")
        node.candidate_hash = evidence_hash
        node.feedback = self._trim(summary)
        node.status = SubgoalStatus.CANDIDATE
        self.version += 1
        return {
            "ok": True,
            "submitted": True,
            "subgoal_id": subgoal_id,
            "evidence_hash": evidence_hash,
            "state": self.snapshot(),
        }

    def _invalidate_descendants(self, subgoal_id: str) -> None:
        invalid = {subgoal_id}
        changed = True
        while changed:
            changed = False
            for node in self.nodes.values():
                if node.id not in invalid and set(node.depends_on) & invalid:
                    invalid.add(node.id)
                    changed = True
        for item in invalid:
            node = self.nodes[item]
            node.status = SubgoalStatus.REJECTED if item == subgoal_id else SubgoalStatus.PENDING
            node.candidate_hash = None
            node.accepted_hash = None
            node.feedback = ""

    def review_subgoal(
        self, subgoal_id: str, decision: str, evidence_hash: str, feedback: str
    ) -> dict[str, Any]:
        node = self.nodes.get(subgoal_id)
        if node is None:
            return self._error("unknown subgoal")
        decision = decision.strip().lower()
        if decision == "reject":
            self._invalidate_descendants(subgoal_id)
            node.feedback = self._trim(feedback)
            self.version += 1
            self._activate_ready()
            return {
                "ok": True,
                "decision": "reject",
                "accepted": False,
                "subgoal_id": subgoal_id,
                "state": self.snapshot(),
            }
        if decision != "accept":
            return self._error("decision must be accept or reject")
        if node.status is not SubgoalStatus.CANDIDATE:
            return self._error("subgoal has no submitted candidate")
        if not evidence_hash or evidence_hash != node.candidate_hash:
            return self._error("critic evidence does not match the submitted candidate")
        if evidence_hash not in node.critic_verified:
            return self._error("critic must independently compile the exact candidate")

        node.status = SubgoalStatus.ACCEPTED
        node.accepted_hash = evidence_hash
        node.feedback = self._trim(feedback)
        self.version += 1
        self._activate_ready()
        return {
            "ok": True,
            "decision": "accept",
            "accepted": True,
            "subgoal_id": subgoal_id,
            "evidence_hash": evidence_hash,
            "state": self.snapshot(),
        }

    def finish_run(self, final_subgoal_id: str, evidence_hash: str) -> dict[str, Any]:
        node = self.nodes.get(final_subgoal_id)
        if node is None:
            return self._error("unknown final subgoal")
        incomplete = [
            item.id for item in self.nodes.values() if item.status is not SubgoalStatus.ACCEPTED
        ]
        if incomplete:
            return self._error(f"all subgoals must be accepted first: {incomplete}")
        if node.accepted_hash != evidence_hash:
            return self._error("final evidence does not match the accepted candidate")

        ancestors: set[str] = set()
        frontier = list(node.depends_on)
        while frontier:
            item = frontier.pop()
            if item in ancestors:
                continue
            ancestors.add(item)
            frontier.extend(self.nodes[item].depends_on)
        expected = set(self.nodes) - {final_subgoal_id}
        if ancestors != expected:
            return self._error("final subgoal must depend on every other subgoal")
        return {
            "ok": True,
            "run_complete": True,
            "final_subgoal_id": final_subgoal_id,
            "evidence_hash": evidence_hash,
            "state": self.snapshot(),
        }

    def route_next_agent(
        self, target: str, reason: str, subgoal_id: str = ""
    ) -> dict[str, Any]:
        target = target.strip().lower()
        if target not in {"reasoner", "engineer", "critic"}:
            return self._error("target must be reasoner, engineer, or critic")
        if target == "engineer":
            if not self.plan_ready:
                return self._error("define two leaf subgoals and one integration subgoal first")
            blocked = [
                node.id for node in self.nodes.values() if node.status is SubgoalStatus.BLOCKED
            ]
            if blocked:
                return self._error(f"revise blocked subgoals before routing: {blocked}")
            if self.active_id is None:
                return self._error("there is no active subgoal for the engineer")
        if target == "critic" and not any(
            node.status is SubgoalStatus.CANDIDATE for node in self.nodes.values()
        ):
            return self._error("submit a compiler-verified candidate before critic routing")
        return {
            "ok": True,
            "handoff_target": target,
            "route_kind": "agent_tool_handoff",
            "reason": self._trim(reason, 300),
            "subgoal_id": subgoal_id,
            "state_version": self.version,
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "active_subgoal": self.active_id,
            "plan_ready": self.plan_ready,
            "forced_recoveries": self.forced_recoveries,
            "strategy_revisions": self.strategy_revisions,
            "limits": {
                "max_nodes": self.max_nodes,
                "max_failures": self.max_failures,
                "max_forced_replans": self.max_forced_replans,
            },
            "nodes": [
                {
                    "id": node.id,
                    "objective": node.objective,
                    "depends_on": list(node.depends_on),
                    "status": node.status.value,
                    "attempts": node.attempts,
                    "consecutive_failures": node.consecutive_failures,
                    "candidate_hash": node.candidate_hash,
                    "accepted_hash": node.accepted_hash,
                    "failures": list(node.failures),
                    "feedback": node.feedback,
                }
                for node in self.nodes.values()
            ],
        }


def make_subgoal_tools(compiler, ledger: SubgoalLedger) -> dict[str, Any]:
    """Create role-scoped tools sharing one trial-local ledger."""

    def plan_subgoal(subgoal_id: str, objective: str, depends_on: list[str]) -> dict:
        """Create or revise one dependency-aware subgoal."""
        return ledger.plan_subgoal(subgoal_id, objective, depends_on)

    def read_subgoals() -> dict:
        """Read the compact current subgoal graph and attempt state."""
        return ledger.snapshot()

    def check_lean(
        code: str, subgoal_id: str, purpose: str = "subgoal"
    ) -> dict[str, Any]:
        """Compile engineer Lean code as a probe, subgoal, or final attempt."""
        if purpose not in {"probe", "subgoal", "final"}:
            return {"ok": False, "error": "purpose must be probe, subgoal, or final"}
        result = compiler.check(code)
        payload = result.to_dict()
        evidence = ledger.record_compile(
            code=code,
            subgoal_id=subgoal_id,
            purpose=purpose,
            compiled=result.compiled,
            summary=result.summary,
            reviewer=False,
        )
        payload.update(evidence)
        payload["subgoal_id"] = subgoal_id
        payload["purpose"] = purpose
        if evidence.get("recovery_required"):
            payload.update(
                {
                    "handoff_target": "reasoner",
                    "route_kind": "failed_compile_recovery",
                    "reason": f"{subgoal_id} reached the failed proof limit",
                    "state": ledger.snapshot(),
                }
            )
        if evidence.get("recovery_exhausted"):
            payload["terminate_reason"] = "stuck"
        return payload

    def submit_subgoal(subgoal_id: str, evidence_hash: str, summary: str) -> dict:
        """Submit a compiler-verified active subgoal for critic review."""
        return ledger.submit_subgoal(subgoal_id, evidence_hash, summary)

    def review_lean(code: str, subgoal_id: str) -> dict[str, Any]:
        """Independently compile the critic's exact candidate."""
        result = compiler.check(code)
        payload = result.to_dict()
        payload.update(
            ledger.record_compile(
                code=code,
                subgoal_id=subgoal_id,
                purpose="review",
                compiled=result.compiled,
                summary=result.summary,
                reviewer=True,
            )
        )
        payload["subgoal_id"] = subgoal_id
        payload["purpose"] = "review"
        return payload

    def review_subgoal(
        subgoal_id: str, decision: str, evidence_hash: str = "", feedback: str = ""
    ) -> dict:
        """Accept or reject one candidate using independent critic evidence."""
        return ledger.review_subgoal(subgoal_id, decision, evidence_hash, feedback)

    def route_next_agent(target: str, reason: str, subgoal_id: str = "") -> dict:
        """Request the next allowed reasoning agent with a concrete reason."""
        return ledger.route_next_agent(target, reason, subgoal_id)

    def finish_run(final_subgoal_id: str, evidence_hash: str) -> dict:
        """Finish only when the complete dependency graph is critic-accepted."""
        return ledger.finish_run(final_subgoal_id, evidence_hash)

    return {
        "plan_subgoal": plan_subgoal,
        "read_subgoals": read_subgoals,
        "check_lean": check_lean,
        "submit_subgoal": submit_subgoal,
        "review_lean": review_lean,
        "review_subgoal": review_subgoal,
        "route_next_agent": route_next_agent,
        "finish_run": finish_run,
    }
