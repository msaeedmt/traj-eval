"""AG2-based four-role agent substrate (Methodology §4.1).

Built incrementally: planner (1a) -> + engineer (1b) -> + critic (1c)
-> + executor & group chat (1d). This package is the substrate the
non-invasive observer (O1) instruments; it does not depend on trace_core
except to reuse the canonical role names.
"""

from traj_eval.agents.config import build_llm_config
from traj_eval.agents.group_chat import build_team
from traj_eval.agents.observer import TraceObserver, make_trial_meta
from traj_eval.agents.roles import (
    make_critic,
    make_engineer,
    make_executor,
    make_planner,
)
from traj_eval.agents.routing import RoutingLedger

__all__ = [
    "RoutingLedger",
    "TraceObserver",
    "build_llm_config",
    "build_team",
    "make_critic",
    "make_engineer",
    "make_executor",
    "make_planner",
    "make_trial_meta",
]
