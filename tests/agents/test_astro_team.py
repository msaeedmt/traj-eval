"""Tests for the astro team wiring.

No LLM is called: the routing graph, the tool registration, and the progress
verdict are all inspectable statically, and the run itself is driven by feeding
messages through the group chat's speaker-selection function -- the same
technique ``test_free_routing.py`` uses for Lean.
"""

from __future__ import annotations

import os
import types

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-dummy")

from autogen import LLMConfig  # noqa: E402

from traj_eval.agents.astro_roles import (  # noqa: E402
    EPOCH_HINT,
    make_astro_critic,
    make_astro_engineer,
    make_astro_planner,
)
from traj_eval.agents.astro_team import (  # noqa: E402
    ASTRO_PROGRESS_KEY,
    TOOL_FIT,
    TOOL_PERIODOGRAM,
    TOOL_RESIDUAL,
    TOOL_SUBMIT,
    astro_routing_config,
    astro_task_prompt,
    build_astro_free_team,
    build_astro_tools,
)
from traj_eval.trace_core.schema import AgentRole  # noqa: E402

# Same construction as the Lean routing tests: a dummy config so agents can be
# built without an LLM ever being called.
_DUMMY = LLMConfig({"api_type": "openai", "model": "gpt-4o-mini", "api_key": "sk-dummy"})


@pytest.fixture(scope="module")
def llm_config():
    return _DUMMY


# --------------------------------------------------------------------------
# routing graph
# --------------------------------------------------------------------------


def test_entry_is_the_planner() -> None:
    """Model selection comes first: the planner decides count and periods."""
    assert astro_routing_config().entry is AgentRole.PLANNER


def test_only_the_critic_may_submit() -> None:
    """Submission is the budgeted action, so it is what gives the critic power.

    If the engineer could submit, the critic would be decorative and Expected
    Result 1 (critic reduces perseveration) would not be testable.
    """
    roles = astro_routing_config().roles
    assert TOOL_SUBMIT in roles[AgentRole.CRITIC].tools
    assert TOOL_SUBMIT not in roles[AgentRole.ENGINEER].tools
    assert TOOL_SUBMIT not in roles[AgentRole.PLANNER].tools


def test_only_the_critic_may_terminate() -> None:
    roles = astro_routing_config().roles
    assert roles[AgentRole.CRITIC].can_terminate
    assert not roles[AgentRole.PLANNER].can_terminate
    assert not roles[AgentRole.ENGINEER].can_terminate


def test_planner_holds_periodogram_and_residual() -> None:
    """Grounded model selection, but no fitting: the planner hypothesises.

    The periodogram makes its period choice recomputable against the alias
    family. The residual view was added after the first two-planet trial, where
    an escalated planner had no way to see the surviving signal for itself: it
    re-ran the raw periodogram, got byte-identical results, and had to take the
    engineer's word for the 15.93 d peak. With rv_residual its add-a-planet
    decision is a logged tool call an anchor can check.
    """
    tools = astro_routing_config().roles[AgentRole.PLANNER].tools
    assert tools == frozenset({TOOL_PERIODOGRAM, TOOL_RESIDUAL})


def test_planner_cannot_fit_or_submit() -> None:
    """Residual access must not become model-building access.

    If the planner could fit, the planner/engineer split would collapse and
    Expected Result 2 (planner errors propagate more silently than engineer
    errors) would have no separable roles to compare.
    """
    tools = astro_routing_config().roles[AgentRole.PLANNER].tools
    assert TOOL_FIT not in tools
    assert TOOL_SUBMIT not in tools


def test_engineer_can_escalate_back_to_the_planner() -> None:
    """The planner owns the planet count, so residual signal must escalate."""
    targets = astro_routing_config().roles[AgentRole.ENGINEER].handoff_targets
    assert AgentRole.PLANNER in targets
    assert AgentRole.CRITIC in targets


def test_critic_can_send_work_to_either_role() -> None:
    """A bad fit goes to the engineer; a wrong model goes to the planner."""
    targets = astro_routing_config().roles[AgentRole.CRITIC].handoff_targets
    assert targets == frozenset({AgentRole.ENGINEER, AgentRole.PLANNER})


def test_no_executor_role_in_the_config() -> None:
    """The executor is the controller's mechanical tool runner, not a peer."""
    assert AgentRole.EXECUTOR not in astro_routing_config().roles


# --------------------------------------------------------------------------
# the verifier seam
# --------------------------------------------------------------------------


def test_the_verifier_is_the_fitter_not_the_submitter() -> None:
    """rv_fit drives the no-progress bound; rv_submit could never reach it.

    A submission budget of 3-10 cannot trip a bound of 6, whereas repeated
    non-converging fits are exactly the thrashing the bound exists to catch.
    """
    config = astro_routing_config()
    assert config.progress_verdict is not None

    def result(payload: dict) -> dict:
        return {"tool_responses": [{"id": "t", "content": repr(payload)}]}

    assert config.read_progress(result({ASTRO_PROGRESS_KEY: True})) is True
    assert config.read_progress(result({ASTRO_PROGRESS_KEY: False})) is False
    # Lean's key must be invisible here, or the two domains would share a bound
    # while measuring different things.
    assert config.read_progress(result({"compiled": False})) is None


def test_exploration_does_not_count_toward_the_no_progress_bound(two_planet_task) -> None:
    """Periodogram and residual results must read as 'not a verification step'."""
    task, truth = two_planet_task
    tools, _ = build_astro_tools(task, truth)
    config = astro_routing_config()

    for name in (TOOL_PERIODOGRAM, TOOL_RESIDUAL):
        payload = tools[name]()
        assert ASTRO_PROGRESS_KEY not in payload, f"{name} must not report ok"
        message = {"tool_responses": [{"id": "t", "content": repr(payload)}]}
        assert config.read_progress(message) is None


def test_fit_and_submit_do_report_progress(two_planet_task) -> None:
    task, truth = two_planet_task
    tools, _ = build_astro_tools(task, truth)
    assert ASTRO_PROGRESS_KEY in tools[TOOL_FIT]([11.2])
    assert ASTRO_PROGRESS_KEY in tools[TOOL_SUBMIT]([{"P_days": 11.2}])


# --------------------------------------------------------------------------
# tool assembly
# --------------------------------------------------------------------------


def test_build_astro_tools_returns_all_four(two_planet_task) -> None:
    task, truth = two_planet_task
    tools, submit_tool = build_astro_tools(task, truth)
    assert set(tools) == {TOOL_PERIODOGRAM, TOOL_FIT, TOOL_RESIDUAL, TOOL_SUBMIT}
    assert submit_tool.max_attempts == task.max_submissions


def test_every_configured_tool_exists(two_planet_task) -> None:
    """A role listing a tool nobody built would make its requests unroutable."""
    task, truth = two_planet_task
    tools, _ = build_astro_tools(task, truth)
    for spec in astro_routing_config().roles.values():
        assert spec.tools <= set(tools), f"{spec.role} lists an unbuilt tool"


def test_submit_tool_is_the_returned_instance(two_planet_task) -> None:
    """The caller must keep the stateful submit tool: the offline validator and
    the perseveration detector read its attempt list after the run."""
    task, truth = two_planet_task
    tools, submit_tool = build_astro_tools(task, truth)
    tools[TOOL_SUBMIT](
        [{"P_days": 11.2, "m_sin_i_mjup": 0.5, "e": 0.0, "omega_rad": 0.0, "l_rad": 0.0}]
    )
    assert submit_tool.n_attempts == 1


def test_only_the_submit_tool_can_see_the_truth(two_planet_task) -> None:
    """The other three are built from the agent-visible task alone."""
    task, truth = two_planet_task
    _, submit_tool = build_astro_tools(task, truth)
    assert submit_tool.truth is truth

    from traj_eval.tools.rv_fit import RvFit
    from traj_eval.tools.rv_periodogram import RvPeriodogram
    from traj_eval.tools.rv_residual import RvResidual

    for cls in (RvPeriodogram, RvFit, RvResidual):
        instance = cls(task)
        assert not hasattr(instance, "truth")
        for value in vars(instance).values():
            assert value is not truth


# --------------------------------------------------------------------------
# the opening prompt
# --------------------------------------------------------------------------


def test_prompt_states_the_observations_and_the_gate(two_planet_task) -> None:
    task, _ = two_planet_task
    prompt = astro_task_prompt(task)
    assert str(task.observation.n_obs) in prompt
    assert str(task.max_submissions) in prompt
    # The conjunction gate must be stated, or the team cannot know what it needs.
    for fragment in ("delta-BIC", "1.5x", "planet count"):
        assert fragment in prompt


def test_prompt_leaks_no_truth(two_planet_task) -> None:
    """The opening message is built from AstroTask alone."""
    task, truth = two_planet_task
    prompt = astro_task_prompt(task)
    for planet in truth.planets:
        assert f"{planet.P_days:.6g}" not in prompt
    assert str(len(truth.planets)) not in prompt.split("planets")[0][-40:]


# --------------------------------------------------------------------------
# prompts and the grounding flag
# --------------------------------------------------------------------------


def test_epoch_hint_is_off_by_default(llm_config) -> None:
    """Format fragility must occur at its natural rate unless we intervene.

    Stargazer's agent had the schema available and still used the wrong epoch, so
    available-but-not-salient is the faithful reproduction.
    """
    for factory in (make_astro_planner, make_astro_engineer, make_astro_critic):
        assert EPOCH_HINT not in factory(llm_config).system_message


def test_epoch_hint_can_be_switched_on(llm_config) -> None:
    """As a flag it belongs to the grounding axis of the experimental design."""
    for factory in (make_astro_planner, make_astro_engineer, make_astro_critic):
        assert EPOCH_HINT in factory(llm_config, epoch_hint=True).system_message


def test_agent_names_match_the_schema_roles(llm_config) -> None:
    """The observer maps agent name to schema role with no translation table."""
    assert make_astro_planner(llm_config).name == AgentRole.PLANNER.value
    assert make_astro_engineer(llm_config).name == AgentRole.ENGINEER.value
    assert make_astro_critic(llm_config).name == AgentRole.CRITIC.value


def test_prompts_name_only_the_tools_the_role_holds(llm_config) -> None:
    """A prompt advertising a tool the role cannot call invites dead requests."""
    roles = astro_routing_config().roles
    for factory, role in (
        (make_astro_planner, AgentRole.PLANNER),
        (make_astro_engineer, AgentRole.ENGINEER),
        (make_astro_critic, AgentRole.CRITIC),
    ):
        message = factory(llm_config).system_message
        allowed = roles[role].tools
        for tool in (TOOL_PERIODOGRAM, TOOL_FIT, TOOL_RESIDUAL, TOOL_SUBMIT):
            if f"{tool}(" in message:
                assert tool in allowed, f"{role} prompt offers {tool} it cannot call"


def test_prompts_state_their_marker_lines(llm_config) -> None:
    """Without a marker the controller cannot route and the team stalls."""
    assert "HANDOFF: engineer" in make_astro_planner(llm_config).system_message
    engineer = make_astro_engineer(llm_config).system_message
    assert "HANDOFF: critic" in engineer and "HANDOFF: planner" in engineer
    critic = make_astro_critic(llm_config).system_message
    assert "VERDICT: APPROVE" in critic and "HANDOFF: engineer" in critic


# --------------------------------------------------------------------------
# the assembled team
# --------------------------------------------------------------------------


def test_team_registers_each_tool_with_exactly_its_roles(llm_config, two_planet_task) -> None:
    task, truth = two_planet_task
    tools, _ = build_astro_tools(task, truth)
    _manager, _user, groupchat, _state = build_astro_free_team(llm_config, tools=tools)

    by_name = {agent.name: agent for agent in groupchat.agents}
    roles = astro_routing_config().roles
    for role, spec in roles.items():
        agent = by_name[role.value]
        registered = {entry["function"]["name"] for entry in (agent.llm_config.get("tools") or [])}
        assert spec.tools <= registered, f"{role} is missing {spec.tools - registered}"
        # And nothing it should not have: submit must not reach the engineer.
        assert TOOL_SUBMIT in registered if spec.can_terminate else True
        if role is not AgentRole.CRITIC:
            assert TOOL_SUBMIT not in registered


def test_team_membership(llm_config, two_planet_task) -> None:
    task, truth = two_planet_task
    tools, _ = build_astro_tools(task, truth)
    _manager, _user, groupchat, _state = build_astro_free_team(llm_config, tools=tools)
    names = {agent.name for agent in groupchat.agents}
    assert {"user", AgentRole.EXECUTOR.value} <= names
    assert {AgentRole.PLANNER.value, AgentRole.ENGINEER.value, AgentRole.CRITIC.value} <= names


def _speaker(name: str):
    return types.SimpleNamespace(name=name)


def test_a_full_handoff_path_routes_correctly(llm_config, two_planet_task) -> None:
    """planner -> engineer -> critic -> APPROVE, driven without an LLM.

    Exercises the routing decisions the controller makes on marker lines, which
    is the part of the team that can be wrong independently of any model.
    """
    task, truth = two_planet_task
    tools, _ = build_astro_tools(task, truth)
    _manager, _user, groupchat, state = build_astro_free_team(llm_config, tools=tools)
    select = groupchat.speaker_selection_method

    def say(role: AgentRole, text: str):
        groupchat.messages = groupchat.messages + [
            {"name": role.value, "content": text, "text": text}
        ]
        return select(_speaker(role.value), groupchat)

    nxt = say(AgentRole.PLANNER, "Two planets near 11.2 d and 57.9 d.\nHANDOFF: engineer")
    assert nxt.name == AgentRole.ENGINEER.value

    nxt = say(AgentRole.ENGINEER, "Fitted; residuals at the noise level.\nHANDOFF: critic")
    assert nxt.name == AgentRole.CRITIC.value

    nxt = say(AgentRole.CRITIC, "Periods are not aliases; submitted and passed.\nVERDICT: APPROVE")
    assert state.terminated
    assert state.reason == "clean"


def test_critic_can_send_the_model_back_to_the_planner(llm_config, two_planet_task) -> None:
    """The back-edge that makes a wrong model attributable to the planner."""
    task, truth = two_planet_task
    tools, _ = build_astro_tools(task, truth)
    _manager, _user, groupchat, _state = build_astro_free_team(llm_config, tools=tools)
    select = groupchat.speaker_selection_method

    text = "The 5.6 d period is a harmonic of 11.2 d.\nHANDOFF: planner"
    groupchat.messages = groupchat.messages + [
        {"name": AgentRole.CRITIC.value, "content": text, "text": text}
    ]
    assert select(_speaker(AgentRole.CRITIC.value), groupchat).name == AgentRole.PLANNER.value


def test_planner_cannot_reach_the_critic_directly(llm_config, two_planet_task) -> None:
    """An out-of-graph hand-off is a coordination error, recorded not obeyed."""
    task, truth = two_planet_task
    tools, _ = build_astro_tools(task, truth)
    _manager, _user, groupchat, state = build_astro_free_team(llm_config, tools=tools)
    select = groupchat.speaker_selection_method

    text = "Skipping the fit.\nHANDOFF: critic"
    groupchat.messages = groupchat.messages + [
        {"name": AgentRole.PLANNER.value, "content": text, "text": text}
    ]
    nxt = select(_speaker(AgentRole.PLANNER.value), groupchat)
    assert nxt.name != AgentRole.CRITIC.value
    assert state.invalid_handoffs >= 1
