from __future__ import annotations

import json

import pytest

pytest.importorskip("autogen", reason="agents extra (ag2) not installed")

from autogen import LLMConfig

from traj_eval.agents.lean_routing_ablation import (
    ARM_PROVENANCE,
    COMMON_CRITIC_PROMPT,
    COMMON_ENGINEER_PROMPT,
    COMMON_REASONER_PROMPT,
    CONTROLLER_STUCK_PROBES,
    RoutingArm,
    TOOL_SUBSTRATE_PROVENANCE,
    build_routing_ablation_team,
    evaluate_controller_stuck_probe,
    parse_controller_decision,
    worker_prompts,
)
from traj_eval.trace_core.schema import AgentRole

_DUMMY = LLMConfig(
    {"api_type": "openai", "model": "gpt-4o-mini", "api_key": "sk-dummy"}
)


class _Speaker:
    def __init__(self, name: str):
        self.name = name


def _tool(value: str) -> str:
    """Fake experiment tool."""
    return value


def _build(arm: RoutingArm, *, workers: int = 20, total: int = 20):
    _, _, groupchat, state = build_routing_ablation_team(
        _DUMMY,
        arm=arm,
        tools={
            "check_lean": _tool,
            "search_lemmas": _tool,
            "try_tactic": _tool,
            "show_goals": _tool,
        },
        max_worker_turns=workers,
        max_total_model_calls=total,
        controller_llm_config=_DUMMY if "central" in arm.value else None,
    )
    return groupchat, state


def _append(groupchat, name: str, content: str | None, **extra):
    groupchat.messages = groupchat.messages + [
        {"name": name, "content": content, **extra}
    ]


def _controller(groupchat):
    return next(agent for agent in groupchat.agents if agent.name == "system")


def test_mathematical_prompts_are_shared_across_arms():
    for arm in RoutingArm:
        prompts = worker_prompts(arm)
        assert prompts[AgentRole.REASONER].startswith(COMMON_REASONER_PROMPT)
        assert prompts[AgentRole.ENGINEER].startswith(COMMON_ENGINEER_PROMPT)
        assert prompts[AgentRole.CRITIC].startswith(COMMON_CRITIC_PROMPT)


def test_arm_provenance_is_preregistered():
    assert ARM_PROVENANCE[RoutingArm.LEGACY_DETERMINISTIC] == "c961421"
    assert ARM_PROVENANCE[RoutingArm.UPSTREAM_FREE] == "74f275e"
    assert TOOL_SUBSTRATE_PROVENANCE == "45f0ab1"


def test_controller_contract_accepts_only_allowed_strict_json():
    allowed = frozenset({AgentRole.ENGINEER})
    valid = {
        "content": json.dumps(
            {"next_role": "engineer", "reason": "formalise the strategy"}
        )
    }
    assert parse_controller_decision(valid, allowed) == (
        AgentRole.ENGINEER,
        "formalise the strategy",
    )
    assert parse_controller_decision(
        {"content": '{"next_role":"critic","reason":"skip"}'}, allowed
    ) is None
    assert parse_controller_decision(
        {"content": '{"next_role":"engineer","reason":"ok","proof":"by"}'},
        allowed,
    ) is None
    assert parse_controller_decision(
        {"content": valid["content"], "tool_calls": [{"function": {}}]}, allowed
    ) is None


@pytest.mark.parametrize("probe", CONTROLLER_STUCK_PROBES, ids=lambda probe: probe.name)
def test_controller_stuck_probes_have_machine_checked_expected_route(probe):
    response = {
        "content": json.dumps(
            {
                "next_role": probe.expected_role.value,
                "reason": "recover from the visible lack of progress",
            }
        )
    }

    assert evaluate_controller_stuck_probe(probe, response) == (
        True,
        "expected_route",
    )


@pytest.mark.parametrize("probe", CONTROLLER_STUCK_PROBES, ids=lambda probe: probe.name)
def test_controller_stuck_probes_reject_wrong_or_unstructured_route(probe):
    wrong_role = next(role for role in probe.allowed_roles if role is not probe.expected_role)

    assert evaluate_controller_stuck_probe(
        probe,
        {
            "content": json.dumps(
                {"next_role": wrong_role.value, "reason": "continue"}
            )
        },
    ) == (False, f"wrong_route:{wrong_role.value}")
    assert evaluate_controller_stuck_probe(probe, {"content": "ask the engineer"}) == (
        False,
        "invalid_controller_output",
    )


def test_legacy_deterministic_reproduces_fixed_repair_loop():
    groupchat, state = _build(RoutingArm.LEGACY_DETERMINISTIC)
    select = groupchat.speaker_selection_method

    assert select(_Speaker("user"), groupchat).name == "reasoner"
    _append(groupchat, "reasoner", "strategy")
    assert select(_Speaker("reasoner"), groupchat).name == "engineer"
    _append(groupchat, "engineer", "candidate")
    assert select(_Speaker("engineer"), groupchat).name == "critic"
    _append(groupchat, "critic", "VERDICT: REJECT - mismatch")
    assert select(_Speaker("critic"), groupchat).name == "engineer"
    _append(groupchat, "critic", "VERDICT: APPROVE")
    assert select(_Speaker("critic"), groupchat) is None
    assert state.reason == "clean"


def test_upstream_free_obeys_worker_handoff_marker():
    groupchat, state = _build(RoutingArm.UPSTREAM_FREE)
    select = groupchat.speaker_selection_method
    _append(groupchat, "reasoner", "strategy\nHANDOFF: engineer")

    selected = select(_Speaker("reasoner"), groupchat)

    assert selected.name == "engineer"
    assert state.worker_turns == 1
    assert state.invalid_routes == 0


def test_valid_tool_call_resets_invalid_counter_like_upstream_free_routing():
    groupchat, state = _build(RoutingArm.UPSTREAM_FREE)
    select = groupchat.speaker_selection_method
    state.consecutive_invalid = 2
    _append(
        groupchat,
        "engineer",
        None,
        tool_calls=[
            {
                "id": "call-1",
                "function": {"name": "check_lean", "arguments": '{"code":"x"}'},
            }
        ],
    )

    assert select(_Speaker("engineer"), groupchat).name == "executor"
    assert state.consecutive_invalid == 0


@pytest.mark.parametrize("arm", tuple(RoutingArm))
def test_alternating_reasoner_searches_stop_after_eight_completed_calls(arm):
    groupchat, state = _build(arm)
    select = groupchat.speaker_selection_method
    controller = _controller(groupchat) if "central" in arm.value else None
    queries = (
        "ZMod n IsDomain Nat.Prime n",
        "ZMod n IsDomain iff Nat.Prime n",
    )

    for index in range(8):
        _append(
            groupchat,
            "reasoner",
            None,
            tool_calls=[
                {
                    "id": f"search-{index}",
                    "function": {
                        "name": "search_lemmas",
                        "arguments": json.dumps({"query": queries[index % 2]}),
                    },
                }
            ],
        )
        assert select(_Speaker("reasoner"), groupchat).name == "executor"
        _append(groupchat, "executor", "search completed")
        selected = select(_Speaker("executor"), groupchat)
        if index < 7:
            if controller is None:
                assert selected.name == "reasoner"
            else:
                assert selected is controller
                _append(
                    groupchat,
                    "system",
                    '{"next_role":"reasoner","reason":"inspect retrieval"}',
                )
                assert select(controller, groupchat).name == "reasoner"
        else:
            assert selected is None

    assert state.reason == "stuck"
    assert state.retrieval_only_streak == 8
    assert state.max_retrieval_only_streak_seen == 8
    assert state.max_identical_calls_seen == 1


def test_non_search_worker_progress_resets_retrieval_only_streak():
    groupchat, state = _build(RoutingArm.LEGACY_DETERMINISTIC)
    select = groupchat.speaker_selection_method
    state.retrieval_only_streak = 3
    state.max_retrieval_only_streak_seen = 3
    _append(groupchat, "reasoner", "The strategy is ready for formalisation.")

    assert select(_Speaker("reasoner"), groupchat).name == "engineer"
    assert state.retrieval_only_streak == 0
    assert state.max_retrieval_only_streak_seen == 3


def test_parallel_reasoner_searches_count_completed_calls_not_executor_turns():
    groupchat, state = _build(RoutingArm.LEGACY_DETERMINISTIC)
    select = groupchat.speaker_selection_method

    for batch in range(4):
        _append(
            groupchat,
            "reasoner",
            None,
            tool_calls=[
                {
                    "id": f"search-{batch}-{index}",
                    "function": {
                        "name": "search_lemmas",
                        "arguments": json.dumps(
                            {"query": f"ZMod query {batch}-{index}"}
                        ),
                    },
                }
                for index in range(2)
            ],
        )
        assert select(_Speaker("reasoner"), groupchat).name == "executor"
        _append(groupchat, "executor", "both searches completed")
        selected = select(_Speaker("executor"), groupchat)
        if batch < 3:
            assert selected.name == "reasoner"
        else:
            assert selected is None

    assert state.reason == "stuck"
    assert state.worker_turns == 4
    assert state.retrieval_only_streak == 8
    assert state.max_retrieval_only_streak_seen == 8


def test_unauthorized_tool_attempt_does_not_reset_retrieval_only_streak():
    groupchat, state = _build(RoutingArm.LEGACY_DETERMINISTIC)
    select = groupchat.speaker_selection_method
    state.retrieval_only_streak = 3
    state.max_retrieval_only_streak_seen = 3
    _append(
        groupchat,
        "reasoner",
        None,
        tool_calls=[
            {
                "id": "unauthorized-check",
                "function": {"name": "check_lean", "arguments": '{"code":"x"}'},
            }
        ],
    )

    assert select(_Speaker("reasoner"), groupchat).name == "reasoner"
    assert state.invalid_routes == 1
    assert state.retrieval_only_streak == 3


def test_invalid_free_response_cannot_evade_retrieval_only_limit():
    groupchat, state = _build(RoutingArm.UPSTREAM_FREE)
    select = groupchat.speaker_selection_method
    queries = (
        "ZMod n IsDomain Nat.Prime n",
        "ZMod n IsDomain iff Nat.Prime n",
    )

    for index in range(8):
        _append(
            groupchat,
            "reasoner",
            None,
            tool_calls=[
                {
                    "id": f"search-{index}",
                    "function": {
                        "name": "search_lemmas",
                        "arguments": json.dumps({"query": queries[index % 2]}),
                    },
                }
            ],
        )
        assert select(_Speaker("reasoner"), groupchat).name == "executor"
        _append(groupchat, "executor", "search completed")
        selected = select(_Speaker("executor"), groupchat)
        if index == 7:
            assert selected is None
            break
        assert selected.name == "reasoner"
        _append(groupchat, "reasoner", "Still searching without a handoff marker.")
        assert select(_Speaker("reasoner"), groupchat).name == "reasoner"

    assert state.reason == "stuck"
    assert state.invalid_routes == 7
    assert state.retrieval_only_streak == 8


def test_valid_non_search_tool_resets_retrieval_only_streak():
    groupchat, state = _build(RoutingArm.LEGACY_DETERMINISTIC)
    select = groupchat.speaker_selection_method
    state.retrieval_only_streak = 3
    state.max_retrieval_only_streak_seen = 3
    _append(
        groupchat,
        "engineer",
        None,
        tool_calls=[
            {
                "id": "valid-check",
                "function": {"name": "check_lean", "arguments": '{"code":"x"}'},
            }
        ],
    )

    assert select(_Speaker("engineer"), groupchat).name == "executor"
    assert state.retrieval_only_streak == 0


def test_central_controller_is_separate_from_worker_budget():
    groupchat, state = _build(
        RoutingArm.CENTRAL_WORKER_MATCHED, workers=2, total=2
    )
    select = groupchat.speaker_selection_method
    controller = _controller(groupchat)

    assert select(_Speaker("user"), groupchat) is controller
    _append(
        groupchat,
        "system",
        '{"next_role":"reasoner","reason":"start with strategy"}',
    )
    assert select(controller, groupchat).name == "reasoner"
    _append(groupchat, "reasoner", "strategy")
    assert select(_Speaker("reasoner"), groupchat) is controller

    assert state.worker_turns == 1
    assert state.controller_turns == 1
    assert state.max_total_model_calls is None


def test_total_call_matched_controller_counts_controller_and_worker():
    groupchat, state = _build(
        RoutingArm.CENTRAL_TOTAL_CALL_MATCHED, workers=200, total=2
    )
    select = groupchat.speaker_selection_method
    controller = _controller(groupchat)

    assert select(_Speaker("user"), groupchat) is controller
    _append(
        groupchat,
        "system",
        '{"next_role":"reasoner","reason":"start with strategy"}',
    )
    assert select(controller, groupchat).name == "reasoner"
    _append(groupchat, "reasoner", "strategy")

    assert select(_Speaker("reasoner"), groupchat) is None
    assert state.total_model_calls == 2
    assert state.reason == "cap"


def test_central_controller_records_reasoner_stuck_recovery():
    groupchat, state = _build(RoutingArm.CENTRAL_WORKER_MATCHED)
    select = groupchat.speaker_selection_method
    controller = _controller(groupchat)
    state.last_worker_role = AgentRole.REASONER
    state.after_tool_result = True
    state.last_tool_names = frozenset({"search_lemmas"})
    state.retrieval_only_streak = 2
    _append(
        groupchat,
        "system",
        '{"next_role":"engineer","reason":"retrieval is repeating"}',
    )

    assert select(controller, groupchat).name == "engineer"
    assert state.reasoner_stuck_to_engineer == 1
    assert state.retrieval_only_streak == 0


def test_central_controller_distinguishes_engineer_replan_from_local_retry():
    groupchat, state = _build(RoutingArm.CENTRAL_WORKER_MATCHED)
    select = groupchat.speaker_selection_method
    controller = _controller(groupchat)
    state.last_worker_role = AgentRole.ENGINEER
    state.after_tool_result = True
    state.last_compile_verdict = False
    state.consecutive_failed_compiles = 2
    _append(
        groupchat,
        "system",
        '{"next_role":"reasoner","reason":"proof shape is repeating"}',
    )

    assert select(controller, groupchat).name == "reasoner"
    assert state.engineer_stuck_to_reasoner == 1

    state.after_tool_result = True
    state.consecutive_failed_compiles = 1
    _append(
        groupchat,
        "system",
        '{"next_role":"engineer","reason":"repair the local syntax error"}',
    )
    assert select(controller, groupchat).name == "engineer"
    assert state.engineer_local_retries == 1


def test_all_arms_give_goal_tools_only_to_engineer():
    for arm in RoutingArm:
        groupchat, _ = _build(arm)
        by_name = {agent.name: agent for agent in groupchat.agents}
        names = {
            name: {
                tool["function"]["name"] for tool in agent.llm_config.model_dump()["tools"]
            }
            for name, agent in by_name.items()
            if name in {"reasoner", "engineer", "critic"}
        }
        assert {"try_tactic", "show_goals"} <= names["engineer"]
        assert "try_tactic" not in names["reasoner"]
        assert "show_goals" not in names["critic"]
