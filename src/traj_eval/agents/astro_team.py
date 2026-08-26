"""Astro instantiation of the free-routing controller.

The DOMAIN-CONFIG seam for radial-velocity model fitting, parallel to
``lean_team.py``: it supplies a ``RoutingConfig`` and the matching agents, and
the agnostic controller in ``free_routing.py`` is untouched.

The coordination triangle:

    planner  --TOOL: rv_periodogram | rv_residual--> (executor) --> planner
    planner  --HANDOFF--> engineer
    engineer --TOOL: rv_fit | rv_residual | rv_periodogram--> (executor) --> engineer
    engineer --HANDOFF--> {critic, planner}
    critic   --TOOL: rv_residual | rv_periodogram | rv_submit--> (executor) --> critic
    critic   --HANDOFF--> {engineer, planner}   |   VERDICT: APPROVE (terminate)

Two deliberate asymmetries with the Lean graph:

**Only the critic holds rv_submit.** Submission is what the attempt budget
constrains, so giving it to the critic is what makes the critic structurally
powerful rather than decorative -- and Expected Result 1 (the critic reduces
perseveration relative to a single-agent baseline) is only testable if the critic
can actually block a resubmission.

**The engineer can hand back to the planner.** The planner owns the planet count,
so an engineer that finds residual signal must escalate rather than silently
adding a planet. That back-edge is what makes count decisions attributable to the
planner -- Expected Result 2 depends on it. Trial evidence: on the first
two-planet task the engineer did exactly this, reporting a surviving 15.93 d peak
and escalating rather than adding the planet itself.

The planner holds rv_residual because that back-edge exists. Without it, an
escalated planner could only re-run the raw periodogram -- observed returning
byte-identical results to its first call, a wasted step on the common path -- and
its decision to add a planet rested on the engineer's prose rather than on
anything recomputable. With it, the decision is a logged tool call an anchor can
check, which is what O1 localisation requires. The cross-agent trust channel
survives, since the planner must still accept the engineer's fitted parameters as
the thing to subtract.

The gap between what each role is ALLOWED to reach and what it actually names is
the coordination signal the run records; the allowed sets are permissive enough
for that gap to exist.

Verifier choice: ``rv_fit`` is the domain's verifier for the no-progress bound
(via ``progress_verdict``), not ``rv_submit``. A submission budget of 3-10 can
never reach a bound of 6, whereas repeated non-converging fits are exactly the
"reworded thrashing" the bound exists to catch. ``rv_periodogram`` and
``rv_residual`` return no ``ok`` key at all, so exploration reads as "not a
verification step" and is not penalised.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from autogen import GroupChatManager, LLMConfig, UserProxyAgent

from traj_eval.agents.astro_roles import (
    make_astro_critic,
    make_astro_engineer,
    make_astro_planner,
)
from traj_eval.agents.free_routing import (
    RoleSpec,
    RoutingConfig,
    build_free_routing_team,
    make_key_progress_verdict,
)
from traj_eval.agents.observer import StepContext
from traj_eval.agents.routing import RoutingLedger
from traj_eval.tools.rv_fit import RvFit
from traj_eval.tools.rv_periodogram import RvPeriodogram
from traj_eval.tools.rv_residual import RvResidual
from traj_eval.tools.rv_submit import RvSubmit
from traj_eval.trace_core.schema import AgentRole

# The uniform success key the astro tools report; rv_fit and rv_submit carry it,
# the exploratory tools deliberately do not.
ASTRO_PROGRESS_KEY = "ok"

TOOL_PERIODOGRAM = "rv_periodogram"
TOOL_FIT = "rv_fit"
TOOL_RESIDUAL = "rv_residual"
TOOL_SUBMIT = "rv_submit"


def astro_routing_config(*, max_turns: int = 40) -> RoutingConfig:
    """The planner -> engineer <-> critic coordination graph for RV fitting."""
    return RoutingConfig(
        entry=AgentRole.PLANNER,
        roles={
            AgentRole.PLANNER: RoleSpec(
                role=AgentRole.PLANNER,
                handoff_targets=frozenset({AgentRole.ENGINEER}),
                tools=frozenset({TOOL_PERIODOGRAM, TOOL_RESIDUAL}),
            ),
            AgentRole.ENGINEER: RoleSpec(
                role=AgentRole.ENGINEER,
                handoff_targets=frozenset({AgentRole.CRITIC, AgentRole.PLANNER}),
                tools=frozenset({TOOL_FIT, TOOL_RESIDUAL, TOOL_PERIODOGRAM}),
            ),
            AgentRole.CRITIC: RoleSpec(
                role=AgentRole.CRITIC,
                handoff_targets=frozenset({AgentRole.ENGINEER, AgentRole.PLANNER}),
                tools=frozenset({TOOL_RESIDUAL, TOOL_PERIODOGRAM, TOOL_SUBMIT}),
                can_terminate=True,
            ),
        },
        max_turns=max_turns,
        progress_verdict=make_key_progress_verdict(ASTRO_PROGRESS_KEY),
    )


def build_astro_tools(
    task: Any,
    truth: Any,
    *,
    stargazer_task: Any = None,
    max_attempts: int | None = None,
) -> tuple[dict[str, Callable[..., Any]], RvSubmit]:
    """Instantiate the four tools for one task. Returns (tools, submit_tool).

    The ``RvSubmit`` instance is returned alongside because it is the only
    stateful tool: it accumulates the attempt list the offline validator and the
    perseveration detector read after the run. The caller must keep it.

    Only ``rv_submit`` receives ``truth``; the other three are constructed from
    the agent-visible ``AstroTask`` alone, so no ground truth is reachable from
    the exploratory or fitting paths even by accident.
    """
    submit_tool = RvSubmit(
        task=task,
        truth=truth,
        stargazer_task=stargazer_task,
        max_attempts=max_attempts,
    )
    tools = {
        TOOL_PERIODOGRAM: RvPeriodogram(task).as_tool(),
        TOOL_FIT: RvFit(task).as_tool(),
        TOOL_RESIDUAL: RvResidual(task).as_tool(),
        TOOL_SUBMIT: submit_tool.as_tool(),
    }
    return tools, submit_tool


def astro_task_prompt(task: Any) -> str:
    """The opening message posted to the team: the observations, no truth.

    Built from ``AstroTask`` only. The full RV table would swamp the context, so
    the prompt gives the summary an astronomer would open with and points the
    team at the tools for the data itself -- the tools read the arrays directly,
    so nothing is lost by not inlining them.
    """
    obs = task.observation
    lines = [
        f"Radial-velocity dataset {task.task_id}.",
        "",
        f"- {obs.n_obs} observations over a baseline of {obs.baseline_days:.1f} days",
        f"- median reported uncertainty: {obs.median_sigma_ms:.3g} m/s",
        f"- instruments: {', '.join(obs.instrument_labels) or 'one'}",
        f"- host star mass: {obs.star_mass_sun:.3g} solar masses",
        f"- submission attempts available: {task.max_submissions}",
        "",
        "Recover the planetary system that produced this signal: the number of",
        "planets and each one's orbital parameters. The data is available to your",
        "tools; you do not need it inlined here.",
        "",
        "A submission passes only if it satisfies all four criteria at once: the",
        "model must beat a flat line (delta-BIC), the residual scatter must be",
        "within 1.5x the median reported uncertainty, the orbits must match the",
        "underlying system, and the planet count must be right. A good statistical",
        "fit at the wrong period fails.",
    ]
    if obs.task_description:
        lines += ["", f"Task notes: {obs.task_description}"]
    return "\n".join(lines)


def build_astro_free_team(
    llm_config: LLMConfig,
    *,
    tools: dict[str, Callable[..., Any]],
    max_turns: int = 40,
    epoch_hint: bool = False,
    ledger: RoutingLedger | None = None,
    step_context: StepContext | None = None,
) -> tuple[GroupChatManager, UserProxyAgent, Any, Any]:
    """Build the astro planner/engineer/critic free-routing team.

    ``tools`` maps tool names to functions, as returned by ``build_astro_tools``.
    Only tools named in the config's RoleSpecs are registered; omitting one a
    role lists means that role's requests for it are unroutable -- itself an
    observable coordination outcome rather than a crash.

    ``epoch_hint`` belongs to the grounding axis of the experimental design: it
    appends the l_rad epoch convention to every role prompt. Default off, so the
    format-fragility failure mode occurs at its natural rate.
    """
    config = astro_routing_config(max_turns=max_turns)
    agents = {
        AgentRole.PLANNER: make_astro_planner(llm_config, epoch_hint=epoch_hint),
        AgentRole.ENGINEER: make_astro_engineer(llm_config, epoch_hint=epoch_hint),
        AgentRole.CRITIC: make_astro_critic(llm_config, epoch_hint=epoch_hint),
    }
    return build_free_routing_team(
        llm_config,
        config=config,
        agents=agents,
        tools=tools,
        ledger=ledger,
        step_context=step_context,
    )
