"""YAGNI handoff-summary recovery in the existing free-routing controller."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

pytest.importorskip("autogen", reason="agents extra (ag2) not installed")

from autogen import LLMConfig  # noqa: E402

from traj_eval.agents.free_routing import (  # noqa: E402
    ToolStallHandoff,
    build_free_routing_team,
)
from traj_eval.agents.lean_team import (  # noqa: E402
    ENGINEER_STUCK_HANDOFF_FIELDS,
    ENGINEER_STUCK_HANDOFF_PROMPT,
    REASONER_STUCK_HANDOFF_FIELDS,
    REASONER_STUCK_HANDOFF_PROMPT,
    RECOVERY_TRIANGLE_NO_RETRIEVAL_V1,
    RECOVERY_TRIANGLE_STALL_HANDOFF_V1,
    RECOVERY_TRIANGLE_V1,
    SUPPORTED_LEAN_SETUPS,
    TOOL_ROUTED_SUBGOALS_V1,
    build_lean_free_team,
    lean_routing_config,
)
from traj_eval.agents.roles import (  # noqa: E402
    make_critic,
    make_engineer,
    make_reasoner,
)
from traj_eval.trace_core.schema import AgentRole  # noqa: E402

_DUMMY = LLMConfig(
    {"api_type": "openai", "model": "gpt-4o-mini", "api_key": "test-placeholder"}
)


class _Speaker:
    def __init__(self, name: str) -> None:
        self.name = name


def _search_lemmas(query: str) -> str:
    """Return a deterministic fake retrieval result."""
    return query


def _check_lean(code: str) -> str:
    """Return a deterministic fake compiler result."""
    return code


def _build(
    *,
    reasoner_after: int | None = None,
    engineer_after: int | None = None,
    max_turns: int = 30,
):
    config = lean_routing_config(
        max_turns=max_turns,
        setup=RECOVERY_TRIANGLE_STALL_HANDOFF_V1,
        reasoner_search_handoff_after=reasoner_after,
        engineer_failed_compile_handoff_after=engineer_after,
    )
    agents = {
        AgentRole.REASONER: make_reasoner(_DUMMY),
        AgentRole.ENGINEER: make_engineer(_DUMMY),
        AgentRole.CRITIC: make_critic(_DUMMY),
    }
    _, _, groupchat, state = build_free_routing_team(
        _DUMMY,
        config=config,
        agents=agents,
        tools={"search_lemmas": _search_lemmas, "check_lean": _check_lean},
    )
    return groupchat, state


def _search_message(query: str) -> dict:
    return {
        "name": AgentRole.REASONER.value,
        "content": None,
        "tool_calls": [
            {
                "id": "search",
                "type": "function",
                "function": {
                    "name": "search_lemmas",
                    "arguments": json.dumps({"query": query}),
                },
            }
        ],
    }


def _search_result() -> dict:
    return {
        "name": AgentRole.EXECUTOR.value,
        "content": None,
        "tool_responses": [{"id": "search", "content": "Top matches"}],
    }


def _check_message(code: str) -> dict:
    return {
        "name": AgentRole.ENGINEER.value,
        "content": None,
        "tool_calls": [
            {
                "id": "check",
                "type": "function",
                "function": {
                    "name": "check_lean",
                    "arguments": json.dumps({"code": code}),
                },
            }
        ],
    }


def _check_result(compiled: bool) -> dict:
    result = {"compiled": compiled, "summary": "test verdict"}
    return {
        "name": AgentRole.EXECUTOR.value,
        "content": None,
        "tool_responses": [{"id": "check", "content": repr(result)}],
    }


def _agent(groupchat, role: AgentRole):
    return next(agent for agent in groupchat.agents if agent.name == role.value)


def _complete_search(groupchat, query: str):
    select = groupchat.speaker_selection_method
    groupchat.messages = groupchat.messages + [_search_message(query)]
    assert select(_Speaker(AgentRole.REASONER.value), groupchat).name == AgentRole.EXECUTOR.value
    groupchat.messages = groupchat.messages + [_search_result()]
    return select(_Speaker(AgentRole.EXECUTOR.value), groupchat)


def _complete_compile(groupchat, code: str, *, compiled: bool):
    select = groupchat.speaker_selection_method
    groupchat.messages = groupchat.messages + [_check_message(code)]
    assert select(_Speaker(AgentRole.ENGINEER.value), groupchat).name == AgentRole.EXECUTOR.value
    groupchat.messages = groupchat.messages + [_check_result(compiled)]
    return select(_Speaker(AgentRole.EXECUTOR.value), groupchat)


def _complete_failed_compile(groupchat, code: str):
    return _complete_compile(groupchat, code, compiled=False)


def test_default_controller_keeps_returning_search_results_to_reasoner():
    groupchat, state = _build()

    assert _complete_search(groupchat, "first").name == AgentRole.REASONER.value
    assert _complete_search(groupchat, "second").name == AgentRole.REASONER.value
    assert state.tool_stall_handoffs == 0


def test_default_controller_rejects_a_malformed_mixed_tool_batch():
    groupchat, state = _build()
    message = _search_message("valid member")
    message["tool_calls"].append(
        {
            "id": "malformed",
            "type": "function",
            "function": {"arguments": json.dumps({"query": "missing name"})},
        }
    )
    groupchat.messages = groupchat.messages + [message]

    selected = groupchat.speaker_selection_method(
        _Speaker(AgentRole.REASONER.value), groupchat
    )

    assert selected.name == AgentRole.REASONER.value
    assert state.invalid_handoffs == 1


def test_reasoner_writes_one_bounded_handoff_before_engineer_receives_control():
    groupchat, state = _build(reasoner_after=2)
    reasoner = _agent(groupchat, AgentRole.REASONER)
    base_prompt = reasoner.system_message

    assert _complete_search(groupchat, "first").name == AgentRole.REASONER.value
    assert _complete_search(groupchat, "second").name == AgentRole.REASONER.value
    assert "Retrieval is now exhausted" in reasoner.system_message

    groupchat.messages = groupchat.messages + [
        {
            "name": AgentRole.REASONER.value,
            "content": (
                "RECOVERY_KIND: reasoner_search_stall\n"
                "STRATEGY: use the retrieved commutativity lemma.\n"
                "RETRIEVED_LEMMAS: Nat.add_comm.\n"
                "UNRESOLVED_FORMALISATION: instantiate it at the current goal.\n"
                "NEXT_LEAN_STEP: try exact Nat.add_comm _ _.\n"
                "HANDOFF: engineer"
            ),
        }
    ]
    selected = groupchat.speaker_selection_method(
        _Speaker(AgentRole.REASONER.value), groupchat
    )

    assert selected.name == AgentRole.ENGINEER.value
    assert state.tool_stall_handoffs == 1
    assert state.handoff_prompt_turns == 1
    assert state.handoff_prompt_failures == 0
    assert reasoner.system_message == base_prompt


def test_engineer_writes_compiler_evidence_before_reasoner_receives_control():
    groupchat, state = _build(engineer_after=2)
    engineer = _agent(groupchat, AgentRole.ENGINEER)
    base_prompt = engineer.system_message

    assert _complete_failed_compile(groupchat, "candidate one").name == AgentRole.ENGINEER.value
    assert _complete_failed_compile(groupchat, "candidate two").name == AgentRole.ENGINEER.value
    assert "Local compilation repair is now exhausted" in engineer.system_message

    groupchat.messages = groupchat.messages + [
        {
            "name": AgentRole.ENGINEER.value,
            "content": (
                "RECOVERY_KIND: engineer_compile_stall\n"
                "PROOF_ATTEMPT: rewrite then exact.\n"
                "COMPILER_EVIDENCE: type mismatch at the final application.\n"
                "WHY_STRATEGY_REVIEW: the lemma has the wrong type.\n"
                "STRATEGIC_QUESTION: choose a lemma matching the target.\n"
                "HANDOFF: reasoner"
            ),
        }
    ]
    selected = groupchat.speaker_selection_method(
        _Speaker(AgentRole.ENGINEER.value), groupchat
    )

    assert selected.name == AgentRole.REASONER.value
    assert state.tool_stall_handoffs == 1
    assert state.handoff_prompt_turns == 1
    assert state.handoff_prompt_failures == 0
    assert engineer.system_message == base_prompt


def test_handoff_only_turn_cannot_escape_into_another_tool_loop():
    groupchat, state = _build(reasoner_after=1)
    reasoner = _agent(groupchat, AgentRole.REASONER)
    base_prompt = reasoner.system_message

    assert _complete_search(groupchat, "first").name == AgentRole.REASONER.value
    groupchat.messages = groupchat.messages + [_search_message("ignored handoff")]
    selected = groupchat.speaker_selection_method(
        _Speaker(AgentRole.REASONER.value), groupchat
    )

    assert selected is None
    assert state.terminated and state.reason == "stuck"
    assert state.handoff_prompt_failures == 1
    assert state.tool_stall_handoffs == 0
    assert reasoner.system_message == base_prompt


def test_turn_cap_restores_the_stuck_workers_original_prompt():
    groupchat, state = _build(reasoner_after=1, max_turns=3)
    reasoner = _agent(groupchat, AgentRole.REASONER)
    base_prompt = reasoner.system_message

    assert _complete_search(groupchat, "first").name == AgentRole.REASONER.value
    assert "Retrieval is now exhausted" in reasoner.system_message
    groupchat.messages = groupchat.messages + [
        {"name": AgentRole.REASONER.value, "content": "HANDOFF: engineer"}
    ]

    selected = groupchat.speaker_selection_method(
        _Speaker(AgentRole.REASONER.value), groupchat
    )

    assert selected is None
    assert state.terminated and state.reason == "cap"
    assert reasoner.system_message == base_prompt


def test_marker_only_handoff_is_not_accepted_as_useful_recovery():
    groupchat, state = _build(reasoner_after=1)

    assert _complete_search(groupchat, "first").name == AgentRole.REASONER.value
    groupchat.messages = groupchat.messages + [
        {"name": AgentRole.REASONER.value, "content": "HANDOFF: engineer"}
    ]
    selected = groupchat.speaker_selection_method(
        _Speaker(AgentRole.REASONER.value), groupchat
    )

    assert selected is None
    assert state.terminated and state.reason == "stuck"
    assert state.handoff_prompt_failures == 1


def test_recovery_fields_require_nonempty_values():
    groupchat, state = _build(reasoner_after=1)

    assert _complete_search(groupchat, "first").name == AgentRole.REASONER.value
    groupchat.messages = groupchat.messages + [
        {
            "name": AgentRole.REASONER.value,
            "content": (
                "RECOVERY_KIND: reasoner_search_stall\n"
                "STRATEGY:\n"
                "RETRIEVED_LEMMAS:\n"
                "UNRESOLVED_FORMALISATION:\n"
                "NEXT_LEAN_STEP:\n"
                "HANDOFF: engineer"
            ),
        }
    ]

    selected = groupchat.speaker_selection_method(
        _Speaker(AgentRole.REASONER.value), groupchat
    )

    assert selected is None
    assert state.terminated and state.reason == "stuck"
    assert state.handoff_prompt_failures == 1


def test_recovery_handoff_marker_must_be_the_final_substantive_line():
    groupchat, state = _build(reasoner_after=1)

    assert _complete_search(groupchat, "first").name == AgentRole.REASONER.value
    groupchat.messages = groupchat.messages + [
        {
            "name": AgentRole.REASONER.value,
            "content": (
                "RECOVERY_KIND: reasoner_search_stall\n"
                "STRATEGY: use the retrieved lemma.\n"
                "RETRIEVED_LEMMAS: Nat.add_comm.\n"
                "UNRESOLVED_FORMALISATION: instantiate the lemma.\n"
                "NEXT_LEAN_STEP: try exact Nat.add_comm _ _.\n"
                "HANDOFF: engineer\n"
                "I will keep working after the handoff."
            ),
        }
    ]

    selected = groupchat.speaker_selection_method(
        _Speaker(AgentRole.REASONER.value), groupchat
    )

    assert selected is None
    assert state.terminated and state.reason == "stuck"
    assert state.handoff_prompt_failures == 1


def test_non_search_progress_resets_the_retrieval_streak():
    groupchat, state = _build(reasoner_after=2)
    select = groupchat.speaker_selection_method

    assert _complete_search(groupchat, "first").name == AgentRole.REASONER.value
    groupchat.messages = groupchat.messages + [
        {
            "name": AgentRole.REASONER.value,
            "content": "Strategy ready.\nHANDOFF: engineer",
        }
    ]
    assert select(_Speaker(AgentRole.REASONER.value), groupchat).name == AgentRole.ENGINEER.value
    groupchat.messages = groupchat.messages + [
        {
            "name": AgentRole.ENGINEER.value,
            "content": "Need a revised strategy.\nHANDOFF: reasoner",
        }
    ]
    assert select(_Speaker(AgentRole.ENGINEER.value), groupchat).name == AgentRole.REASONER.value

    assert _complete_search(groupchat, "second").name == AgentRole.REASONER.value
    assert state.tool_stall_handoffs == 0
    assert state.tool_stall_streaks[(AgentRole.REASONER, "search_lemmas")] == 1


def test_successful_compile_resets_the_engineer_stall_streak():
    groupchat, state = _build(engineer_after=2)
    engineer = _agent(groupchat, AgentRole.ENGINEER)
    base_prompt = engineer.system_message

    assert _complete_failed_compile(groupchat, "first").name == AgentRole.ENGINEER.value
    assert state.tool_stall_streaks[(AgentRole.ENGINEER, "check_lean")] == 1
    assert (
        _complete_compile(groupchat, "successful", compiled=True).name
        == AgentRole.ENGINEER.value
    )
    assert state.tool_stall_streaks[(AgentRole.ENGINEER, "check_lean")] == 0
    assert _complete_failed_compile(groupchat, "second").name == AgentRole.ENGINEER.value
    assert state.tool_stall_streaks[(AgentRole.ENGINEER, "check_lean")] == 1
    assert state.handoff_prompt_turns == 0
    assert engineer.system_message == base_prompt


def test_empty_tool_response_does_not_increment_the_stall_streak():
    groupchat, state = _build(reasoner_after=1)
    select = groupchat.speaker_selection_method
    groupchat.messages = groupchat.messages + [_search_message("first")]
    assert (
        select(_Speaker(AgentRole.REASONER.value), groupchat).name
        == AgentRole.EXECUTOR.value
    )
    groupchat.messages = groupchat.messages + [
        {
            "name": AgentRole.EXECUTOR.value,
            "content": None,
            "tool_responses": [],
        }
    ]

    assert (
        select(_Speaker(AgentRole.EXECUTOR.value), groupchat).name
        == AgentRole.REASONER.value
    )
    assert state.tool_stall_streaks[(AgentRole.REASONER, "search_lemmas")] == 0
    assert state.handoff_prompt_turns == 0


def test_lean_config_enables_only_the_requested_recovery_rule():
    baseline = lean_routing_config()
    recovery = lean_routing_config(
        setup=RECOVERY_TRIANGLE_STALL_HANDOFF_V1,
        reasoner_search_handoff_after=2,
        engineer_failed_compile_handoff_after=2,
    )

    assert baseline.tool_stall_handoffs == ()
    assert recovery.tool_stall_handoffs == (
        ToolStallHandoff(
            caller=AgentRole.REASONER,
            tool="search_lemmas",
            after_batches=2,
            target=AgentRole.ENGINEER,
            handoff_prompt=REASONER_STUCK_HANDOFF_PROMPT,
            required_fields=REASONER_STUCK_HANDOFF_FIELDS,
        ),
        ToolStallHandoff(
            caller=AgentRole.ENGINEER,
            tool="check_lean",
            after_batches=2,
            target=AgentRole.REASONER,
            handoff_prompt=ENGINEER_STUCK_HANDOFF_PROMPT,
            required_fields=ENGINEER_STUCK_HANDOFF_FIELDS,
            require_failed_compile=True,
        ),
    )


def test_supported_lean_setups_are_exactly_the_four_personal_arms():
    assert SUPPORTED_LEAN_SETUPS == (
        RECOVERY_TRIANGLE_V1,
        RECOVERY_TRIANGLE_NO_RETRIEVAL_V1,
        RECOVERY_TRIANGLE_STALL_HANDOFF_V1,
        TOOL_ROUTED_SUBGOALS_V1,
    )


def test_stall_and_typed_routing_features_do_not_leak_between_setups():
    baseline = lean_routing_config(setup=RECOVERY_TRIANGLE_V1)
    no_retrieval = lean_routing_config(setup=RECOVERY_TRIANGLE_NO_RETRIEVAL_V1)
    stall = lean_routing_config(setup=RECOVERY_TRIANGLE_STALL_HANDOFF_V1)
    typed = lean_routing_config(setup=TOOL_ROUTED_SUBGOALS_V1)

    assert baseline.tool_stall_handoffs == no_retrieval.tool_stall_handoffs == ()
    assert [rule.after_batches for rule in stall.tool_stall_handoffs] == [2, 2]
    assert typed.tool_stall_handoffs == ()
    assert typed.tool_result_routing is True
    assert typed.allow_marker_handoffs is False
    assert typed.allow_terminal_markers is False
    assert baseline.tool_result_routing is False
    with pytest.raises(ValueError, match="require the stall-handoff setup"):
        lean_routing_config(
            setup=RECOVERY_TRIANGLE_V1,
            reasoner_search_handoff_after=2,
        )

    goal_tool_names = {"try_tactic", "show_goals"}
    assert all(
        spec.tools.isdisjoint(goal_tool_names)
        for config in (baseline, no_retrieval, stall, typed)
        for spec in config.roles.values()
    )


def test_duplicate_caller_tool_rules_are_rejected():
    config = lean_routing_config(
        setup=RECOVERY_TRIANGLE_STALL_HANDOFF_V1,
        reasoner_search_handoff_after=1,
    )
    duplicate = replace(
        config,
        tool_stall_handoffs=(
            config.tool_stall_handoffs[0],
            config.tool_stall_handoffs[0],
        ),
    )
    agents = {
        AgentRole.REASONER: make_reasoner(_DUMMY),
        AgentRole.ENGINEER: make_engineer(_DUMMY),
        AgentRole.CRITIC: make_critic(_DUMMY),
    }

    with pytest.raises(ValueError, match="caller/tool pairs must be unique"):
        build_free_routing_team(
            _DUMMY,
            config=duplicate,
            agents=agents,
            tools={"search_lemmas": _search_lemmas, "check_lean": _check_lean},
        )


def test_missing_stall_caller_agent_is_rejected_at_build():
    config = lean_routing_config(
        setup=RECOVERY_TRIANGLE_STALL_HANDOFF_V1,
        reasoner_search_handoff_after=1,
    )
    agents = {
        AgentRole.ENGINEER: make_engineer(_DUMMY),
        AgentRole.CRITIC: make_critic(_DUMMY),
    }

    with pytest.raises(ValueError, match="caller must have a configured agent"):
        build_free_routing_team(
            _DUMMY,
            config=config,
            agents=agents,
            tools={"search_lemmas": _search_lemmas, "check_lean": _check_lean},
        )


def test_named_stall_setup_enables_both_rules_without_runner_changes():
    manager, user, groupchat, state = build_lean_free_team(
        _DUMMY,
        tools={"search_lemmas": _search_lemmas, "check_lean": _check_lean},
        setup=RECOVERY_TRIANGLE_STALL_HANDOFF_V1,
    )

    assert manager is not None and user is not None and groupchat is not None
    assert _complete_search(groupchat, "first").name == AgentRole.REASONER.value
    assert _complete_search(groupchat, "second").name == AgentRole.REASONER.value
    assert "Retrieval is now exhausted" in _agent(
        groupchat, AgentRole.REASONER
    ).system_message
    assert state.handoff_prompt_turns == 1

    _, _, engineer_chat, engineer_state = build_lean_free_team(
        _DUMMY,
        tools={"search_lemmas": _search_lemmas, "check_lean": _check_lean},
        setup=RECOVERY_TRIANGLE_STALL_HANDOFF_V1,
    )
    assert _complete_failed_compile(engineer_chat, "first").name == AgentRole.ENGINEER.value
    assert _complete_failed_compile(engineer_chat, "second").name == AgentRole.ENGINEER.value
    assert "Local compilation repair is now exhausted" in _agent(
        engineer_chat, AgentRole.ENGINEER
    ).system_message
    assert engineer_state.handoff_prompt_turns == 1
