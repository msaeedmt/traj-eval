from __future__ import annotations

from dataclasses import dataclass

from traj_eval.agents.subgoal_state import SubgoalLedger, make_subgoal_tools


@dataclass
class _Result:
    compiled: bool
    summary: str

    def to_dict(self):
        return {
            "compiled": self.compiled,
            "sorry_free": self.compiled,
            "summary": self.summary,
        }


class _Compiler:
    def __init__(self):
        self.last_code = ""

    def check(self, code: str):
        self.last_code = code
        return _Result("bad" not in code, "compiled" if "bad" not in code else "failed")


def _planned() -> SubgoalLedger:
    ledger = SubgoalLedger(max_failures=3, max_forced_replans=2)
    assert ledger.plan_subgoal("forward", "Prove the forward direction", [])["ok"]
    assert ledger.plan_subgoal("reverse", "Prove the reverse direction", [])["ok"]
    assert ledger.plan_subgoal(
        "final", "Assemble the exact theorem", ["forward", "reverse"]
    )["ok"]
    return ledger


def test_plan_requires_existing_dependencies_and_integration_node():
    ledger = SubgoalLedger()

    missing = ledger.plan_subgoal("final", "assemble", ["forward"])
    ledger.plan_subgoal("forward", "forward", [])
    ledger.plan_subgoal("reverse", "reverse", [])
    not_ready = ledger.route_next_agent("engineer", "start")
    ledger.plan_subgoal("final", "assemble", ["forward", "reverse"])

    assert missing["ok"] is False
    assert not_ready["ok"] is False
    assert ledger.plan_ready is True
    assert ledger.active_id == "forward"


def test_natural_sequential_plan_is_ready_without_artificial_parallel_leaves():
    ledger = SubgoalLedger()
    ledger.plan_subgoal("construction", "Construct the universal object", [])
    ledger.plan_subgoal("uniqueness", "Apply uniqueness", ["construction"])
    final = ledger.plan_subgoal("final", "Integrate the exact theorem", ["uniqueness"])

    assert ledger.plan_ready is True
    assert ledger.route_next_agent("engineer", "start")["ok"] is True
    assert final["required_next_action"]["tool"] == "route_next_agent"


def test_medium_plan_requires_four_nodes():
    ledger = SubgoalLedger(min_nodes=4)
    ledger.plan_subgoal("definitions", "Compile definitions", [])
    ledger.plan_subgoal("construction", "Compile construction", ["definitions"])
    third = ledger.plan_subgoal("uniqueness", "Compile uniqueness", ["construction"])
    fourth = ledger.plan_subgoal("final", "Compile final theorem", ["uniqueness"])

    assert third["state"]["plan_ready"] is False
    assert fourth["state"]["plan_ready"] is True
    assert fourth["state"]["limits"]["min_nodes"] == 4


def test_plan_record_preserves_controller_owned_revision_history():
    ledger = _planned()
    ledger.nodes["forward"].status = type(ledger.nodes["forward"].status).BLOCKED
    ledger.plan_subgoal("forward", "Use a revised forward argument", [])

    record = ledger.plan_record()

    assert record["owner_role"] == "reasoner"
    assert record["persistence_authority"] == "deterministic_controller"
    assert [item["action"] for item in record["history"]] == [
        "created",
        "created",
        "created",
        "revised",
    ]
    assert record["final_state"]["strategy_revisions"] == 1


def test_probe_does_not_hide_failed_proof_recovery():
    ledger = _planned()
    tools = make_subgoal_tools(_Compiler(), ledger)

    tools["check_lean"]("#check Transitive", "forward", "probe")
    first = tools["check_lean"]("bad proof 1", "forward", "subgoal")
    tools["check_lean"]("#check IsTrans", "forward", "probe")
    second = tools["check_lean"]("bad proof 2", "forward", "subgoal")
    third = tools["check_lean"]("bad proof 3", "forward", "subgoal")

    assert first["recovery_required"] is False
    assert second["recovery_required"] is False
    assert third["handoff_target"] == "reasoner"
    assert third["route_kind"] == "failed_compile_recovery"
    assert ledger.nodes["forward"].consecutive_failures == 3


def test_submission_and_acceptance_require_two_compiler_owners():
    ledger = _planned()
    tools = make_subgoal_tools(_Compiler(), ledger)
    code = "example : True := by trivial"

    checked = tools["check_lean"](code, "forward", "subgoal")
    evidence_hash = checked["evidence_hash"]
    submitted = tools["submit_subgoal"]("forward", evidence_hash, "direct proof")
    candidate = tools["read_candidate"]("forward")
    premature = tools["review_subgoal"]("forward", "accept", evidence_hash, "ok")
    reviewed = tools["review_lean"](code, "forward")
    accepted = tools["review_subgoal"](
        "forward", "accept", reviewed["evidence_hash"], "faithful"
    )

    assert submitted["submitted"] is True
    assert candidate["code"] == code
    assert candidate["evidence_hash"] == evidence_hash
    assert premature["ok"] is False
    assert accepted["accepted"] is True
    assert ledger.active_id == "reverse"


def test_successful_subgoal_candidate_is_submitted_and_routes_to_critic():
    ledger = _planned()
    tools = make_subgoal_tools(_Compiler(), ledger, auto_submit_verified=True)

    checked = tools["check_lean"](
        "example : True := by trivial", "forward", "subgoal"
    )

    assert checked["automatic_submission"]["submitted"] is True
    assert checked["handoff_target"] == "critic"
    assert checked["route_kind"] == "verified_candidate_auto_submit"
    assert ledger.nodes["forward"].status.value == "candidate"


def test_compiler_uses_canonical_prelude_and_hashes_normalized_candidate():
    ledger = _planned()
    compiler = _Compiler()
    tools = make_subgoal_tools(
        compiler,
        ledger,
        prelude="import Mathlib\nopen CategoryTheory\nvariable {G : Type}",
    )
    raw = """import Imaginary.Module
open CategoryTheory
variable {G : Type}
example : True := by trivial
"""

    checked = tools["check_lean"](raw, "forward", "subgoal")
    tools["submit_subgoal"]("forward", checked["evidence_hash"], "normalized")
    candidate = tools["read_candidate"]("forward")

    assert compiler.last_code.startswith("import Mathlib\nopen CategoryTheory")
    assert "Imaginary.Module" not in compiler.last_code
    assert compiler.last_code.count("open CategoryTheory") == 1
    assert candidate["code"] == "example : True := by trivial"
    assert checked["canonical_prelude_applied"] is True


def test_rejecting_accepted_dependency_invalidates_descendants():
    ledger = _planned()
    for node in ledger.nodes.values():
        node.status = type(node.status).ACCEPTED
        node.accepted_hash = node.id

    rejected = ledger.review_subgoal("forward", "reject", "", "wrong statement")

    assert rejected["decision"] == "reject"
    assert ledger.nodes["forward"].status.value == "active"
    assert ledger.nodes["final"].status.value == "pending"
    assert ledger.nodes["reverse"].status.value == "accepted"


def test_finish_requires_all_nodes_and_full_dependency_cone():
    ledger = _planned()
    incomplete = ledger.finish_run("final", "final-hash")
    for node in ledger.nodes.values():
        node.status = type(node.status).ACCEPTED
        node.accepted_hash = f"{node.id}-hash"
    complete = ledger.finish_run("final", "final-hash")

    assert incomplete["ok"] is False
    assert complete["run_complete"] is True


def test_forced_replans_are_bounded():
    ledger = SubgoalLedger(max_failures=1, max_forced_replans=2)
    ledger.plan_subgoal("forward", "route one", [])
    ledger.plan_subgoal("reverse", "route two", [])
    ledger.plan_subgoal("final", "combine", ["forward", "reverse"])
    tools = make_subgoal_tools(_Compiler(), ledger)

    first = tools["check_lean"]("bad one", "forward", "subgoal")
    ledger.plan_subgoal("forward", "route one revised", [])
    second = tools["check_lean"]("bad two", "forward", "subgoal")
    ledger.plan_subgoal("forward", "route one revised again", [])
    third = tools["check_lean"]("bad three", "forward", "subgoal")

    assert first["recovery_required"] is True
    assert second["recovery_required"] is True
    assert third["recovery_exhausted"] is True
    assert third["terminate_reason"] == "stuck"


def test_blocked_subgoal_requires_real_revision_and_drops_stale_evidence():
    ledger = SubgoalLedger(max_failures=1)
    ledger.plan_subgoal("forward", "route one", [])
    ledger.plan_subgoal("reverse", "route two", [])
    ledger.plan_subgoal("final", "combine", ["forward", "reverse"])
    tools = make_subgoal_tools(_Compiler(), ledger)

    successful = tools["check_lean"]("first candidate", "forward", "subgoal")
    assert successful["evidence_hash"] in ledger.nodes["forward"].engineer_verified
    tools["check_lean"]("bad candidate", "forward", "subgoal")

    unchanged = ledger.plan_subgoal("forward", "route one", [])
    revised = ledger.plan_subgoal("forward", "use a different route", [])

    assert unchanged["ok"] is False
    assert revised["revised"] is True
    assert ledger.nodes["forward"].engineer_verified == set()
    assert ledger.route_next_agent("engineer", "retry")["ok"] is True


def test_revision_cannot_create_dependency_cycle():
    ledger = _planned()

    result = ledger.plan_subgoal("forward", "cyclic route", ["final"])

    assert result["ok"] is False
    assert "acyclic" in result["error"]


def test_active_and_candidate_gates_control_compile_and_routing():
    ledger = _planned()
    tools = make_subgoal_tools(_Compiler(), ledger)

    inactive = tools["check_lean"]("candidate", "reverse", "subgoal")
    premature_critic = ledger.route_next_agent("critic", "please review")
    premature_review = tools["review_lean"]("candidate", "forward")

    assert inactive["ok"] is False
    assert premature_critic["ok"] is False
    assert premature_review["ok"] is False


def test_finish_run_requires_independent_final_faithfulness_gate():
    ledger = _planned()
    for node in ledger.nodes.values():
        node.status = type(node.status).ACCEPTED
        node.accepted_hash = f"{node.id}-hash"
    ledger.verified_code["final-hash"] = "theorem target : True := trivial"

    rejected_tools = make_subgoal_tools(
        _Compiler(),
        ledger,
        final_validator=lambda code: {"passed": False, "statement_preserved": False},
    )
    rejected = rejected_tools["finish_run"]("final", "final-hash")

    accepted_tools = make_subgoal_tools(
        _Compiler(),
        ledger,
        final_validator=lambda code: {"passed": True, "statement_preserved": True},
    )
    accepted = accepted_tools["finish_run"]("final", "final-hash")

    assert rejected["ok"] is False
    assert rejected["final_validation"]["statement_preserved"] is False
    assert "run_complete" not in rejected
    assert accepted["run_complete"] is True
    assert accepted["final_validation"]["passed"] is True
