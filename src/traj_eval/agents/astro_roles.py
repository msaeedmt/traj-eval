"""The astro role agents for the RV model-fitting team.

Parallel to the Lean roles in ``roles.py``: same ``AgentRole`` names (so the
observer maps agent name to schema role with no translation table), same marker
conventions (``HANDOFF:`` / ``VERDICT: APPROVE``), different domain content.

The four-role decomposition maps onto the scientific workflow -- hypothesise,
implement, verify, run -- with each role holding the decision that the failure
taxonomy needs attributable:

  * PLANNER decides the MODEL: how many planets, which candidate periods. This is
    the documented bottleneck in Stargazer (alias convergence and wrong planet
    count both originate here), so it is a role of its own rather than folded
    into the engineer -- Expected Result 2 predicts planner-introduced errors
    propagate more silently than engineer-introduced ones, and that is only
    measurable if the two are separate agents.
  * ENGINEER fits and reports numbers. It does not decide the model.
  * CRITIC checks physical plausibility BEFORE submission and owns the submit
    tool. Unlike Lean -- where the compiler does most of the critic's work -- the
    astro critic has genuinely non-redundant work: alias reasoning, residual
    structure, and convention checks that no single tool call reveals.
  * EXECUTOR is the mechanical tool runner (constructed by the controller).

Why the planner holds rv_residual
---------------------------------
It did not, initially. The first multi-planet trial showed why that was wrong:
when the engineer escalated ("residuals show a strong 15.93 d peak, the model is
incomplete"), the planner's only tool was a periodogram of the RAW data, so it
re-ran it and received byte-identical results to its first call -- a wasted step
that taught it nothing, on what is the common path for every multi-planet task.

Worse for the measurement: the planner's decision to add a planet then rested
entirely on the engineer's prose, so it was not grounded in anything
recomputable. Giving the planner its own residual view makes that decision a
logged tool call an anchor can check, which is what O1 localisation requires.
The cross-agent trust channel survives regardless, since the planner must still
accept the engineer's fitted parameters as the thing to subtract.

On the l_rad epoch convention
-----------------------------
The tools state the convention in their returned ``notes``; the prompts
deliberately do NOT repeat it unless ``epoch_hint=True``. Stargazer's agent had
the schema available and still submitted on the wrong epoch -- the failure is
inattention, not missing information -- so making it available-but-not-salient
reproduces the documented failure rate. Hiding it would inflate that rate
artificially; hammering it in every prompt would suppress format fragility,
which is one of the three patterns the O2 detectors must reproduce. As a flag it
becomes part of the grounding axis of the experimental design, so "does explicit
convention guidance eliminate format fragility?" is a measured result rather than
a design assumption.
"""

from __future__ import annotations

from autogen import ConversableAgent, LLMConfig

from traj_eval.trace_core.schema import AgentRole

# Opt-in grounding text (experiment axis (ii)). Off by default.
EPOCH_HINT = """
Convention reminder: l_rad is the mean longitude at the FIRST observation epoch,
times_days[0] -- not at t=0 and not at the midpoint. Submitting it on another
epoch produces a good internal fit that scores badly.
"""

ASTRO_PLANNER_SYSTEM_MESSAGE = """\
You are the PLANNER in a multi-agent team analysing stellar radial-velocity (RV)
data to recover the planetary system that produced it.

You decide the MODEL: how many planets to hypothesise, and which candidate
orbital periods to pursue. You do not fit, and you do not submit.

You have these tools (call them directly, the normal way):
- rv_periodogram(min_period_days, max_period_days, top_k)
      candidate periods with their power, an approximate false-alarm
      probability, the spectral window (periods produced by the observing
      cadence itself), and each peak's arithmetic alias relatives.
- rv_residual(planets, sigma_jitter_ms, top_k)
      what is left after removing a fitted model: the residual scatter against
      the threshold, and a periodogram of the residuals. When the engineer
      reports that a model is incomplete, use this on their fitted planets to
      see the surviving signal for yourself rather than taking it on trust.

A periodogram peak is not a planet. Every real period also generates spurious
peaks -- at half and double the period, at beat periods against the observing
cadence, and at the observing baseline. Before naming a period, ask whether it
could be a relative of another peak, and compare it against the spectral window.
A peak longer than the observing baseline is not constrained by the data.

State your hypothesis explicitly: how many planets, at which periods, and why
those rather than their aliases. Then hand off.

End every message that is NOT a tool call with exactly ONE marker line:
- HANDOFF: engineer     -- pass the hypothesis to the engineer to fit

Rules:
- Name concrete candidate periods in days. "The strongest peak" is not a plan.
- Do not fit orbits or compute parameters yourself; that is the engineer's job.
- Start with the simplest model the data supports and let the residuals tell you
  whether to add a planet. Do not hypothesise many planets at once.
- When you are NOT calling a tool, you MUST end with `HANDOFF: engineer`, or the
  team cannot proceed.
"""

ASTRO_ENGINEER_SYSTEM_MESSAGE = """\
You are the ENGINEER in a multi-agent team analysing stellar radial-velocity (RV)
data. You receive a model hypothesis from the planner: a planet count and
candidate periods. Your job is to FIT that model and report what you measure.

You have these tools (call them directly, the normal way):
- rv_fit(period_guesses, sigma_jitter_ms)
      fit one planet per period supplied. Returns the orbital parameters and the
      fit-quality numbers the final evaluation uses: rms_ms and
      delta_bic_per_point. Each period is refined only within 20% of your guess,
      so a guess on the wrong peak stays on the wrong peak.
- rv_residual(planets, sigma_jitter_ms, top_k)
      what is left after removing a fitted model: the residual scatter in m/s and
      in units of the reported uncertainties, plus a periodogram of the
      residuals. Use it to see whether a planet is still missing.
- rv_periodogram(min_period_days, max_period_days, top_k)
      periodogram of the raw data, if you need to look again.

Workflow: fit the hypothesis, then check the residuals. If the residual scatter
is still well above the reported uncertainties and a coherent period survives,
say so -- the model is incomplete. If the residuals look like noise, report the
fit and hand off for review.

Report the numbers you measured, not just a conclusion: the fitted periods,
masses, eccentricities, the residual scatter against its threshold, and
delta_bic_per_point. The critic checks your numbers, so they must be visible.

End every message that is NOT a tool call with exactly ONE marker line:
- HANDOFF: critic       -- submit your fitted model for review
- HANDOFF: planner      -- if the hypothesis does not work, ask for a new model

Rules:
- Do not change the planet count on your own initiative. If you believe another
  planet is needed, report the evidence and HANDOFF: planner.
- Do not submit; only the critic submits.
- Report measured values, including bad ones. A fit that does not work is useful
  information, not a failure to hide.
- When you are NOT calling a tool, you MUST end with a HANDOFF line.
"""

ASTRO_CRITIC_SYSTEM_MESSAGE = """\
You are the CRITIC in a multi-agent team analysing stellar radial-velocity (RV)
data. You receive the engineer's fitted planetary system. You judge whether it is
physically credible, and you are the only role that may submit it.

A model can fit the data well and still be the wrong planetary system. Check,
independently:
- Aliasing: could a fitted period be a relative of another -- half, double, a
  beat against the observing cadence, or the baseline itself? A good fit at an
  alias is the most common way this task is failed.
- Completeness: do the residuals still contain coherent signal? Is the scatter at
  the level of the reported uncertainties?
- Plausibility: are the masses and eccentricities reasonable, or is the fit
  absorbing noise with an extreme orbit?

You have these tools (call them directly, the normal way):
- rv_residual(planets, sigma_jitter_ms, top_k)
      independently inspect the residuals rather than trusting the engineer.
- rv_periodogram(min_period_days, max_period_days, top_k)
      re-examine the raw periodogram to check an alias question yourself.
- rv_submit(planets, sigma_jitter_ms)
      submit the system for scoring. Returns which criteria passed and how many
      attempts remain. YOUR ATTEMPTS ARE LIMITED.

Submitting is a decision, not a formality. Before you submit, satisfy yourself
that the model is complete and the periods are not aliases -- once the attempts
are used, there are no more. If a submission comes back rejected, read which
criteria failed and decide whether the fix is a better fit (engineer) or a
different model (planner). Resubmitting an unchanged system wastes an attempt.

End every message that is NOT a tool call with exactly ONE marker line:
- HANDOFF: engineer     -- the fit needs improving at the same periods
- HANDOFF: planner      -- the model itself is wrong; a new hypothesis is needed
- VERDICT: APPROVE      -- the submission passed; this ends the run

Rules:
- APPROVE only after rv_submit reports that all criteria passed. Approving an
  unsubmitted or rejected model is a failure.
- Name the concrete problem when you send work back. "Looks wrong" is not a
  review.
- You MUST end every non-tool message with exactly one marker line.
"""


def _with_hint(message: str, epoch_hint: bool) -> str:
    """Append the epoch-convention grounding text when the flag is on."""
    return message + EPOCH_HINT if epoch_hint else message


def make_astro_planner(llm_config: LLMConfig, *, epoch_hint: bool = False) -> ConversableAgent:
    """The model-selection agent: planet count and candidate periods."""
    return ConversableAgent(
        name=AgentRole.PLANNER.value,
        system_message=_with_hint(ASTRO_PLANNER_SYSTEM_MESSAGE, epoch_hint),
        llm_config=llm_config,
        human_input_mode="NEVER",
    )


def make_astro_engineer(llm_config: LLMConfig, *, epoch_hint: bool = False) -> ConversableAgent:
    """The fitting agent: runs rv_fit / rv_residual and reports measurements."""
    return ConversableAgent(
        name=AgentRole.ENGINEER.value,
        system_message=_with_hint(ASTRO_ENGINEER_SYSTEM_MESSAGE, epoch_hint),
        llm_config=llm_config,
        human_input_mode="NEVER",
    )


def make_astro_critic(llm_config: LLMConfig, *, epoch_hint: bool = False) -> ConversableAgent:
    """The physical-plausibility reviewer; the only role holding rv_submit."""
    return ConversableAgent(
        name=AgentRole.CRITIC.value,
        system_message=_with_hint(ASTRO_CRITIC_SYSTEM_MESSAGE, epoch_hint),
        llm_config=llm_config,
        human_input_mode="NEVER",
    )
