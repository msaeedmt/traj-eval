"""Historical AG2 four-role compatibility substrate (Methodology §4.1).

This module preserves the historical Planner -> Engineer -> Critic -> Executor
substrate for old experiments, tests, and traces. Current Lean experiments use
Reasoner, Engineer, and Critic as the three reasoning agents; deterministic
tool execution is a non-agent runtime even where historical traces retain the
``executor`` role value.
"""

from traj_eval.agents.config import build_llm_config
from traj_eval.agents.controller import build_stepped_team
from traj_eval.agents.group_chat import build_team
from traj_eval.agents.observer import StepContext, TraceObserver, make_trial_meta
from traj_eval.agents.plan import Plan, PlanParseError, parse_plan
from traj_eval.agents.roles import (
    make_critic,
    make_engineer,
    make_executor,
    make_planner,
)
from traj_eval.agents.routing import RoutingLedger

__all__ = [
    "Plan",
    "PlanParseError",
    "RoutingLedger",
    "StepContext",
    "TraceObserver",
    "build_llm_config",
    "build_stepped_team",
    "build_team",
    "make_critic",
    "make_engineer",
    "make_executor",
    "make_planner",
    "make_trial_meta",
    "parse_plan",
]
