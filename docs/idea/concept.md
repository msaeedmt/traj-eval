# Traj-Eval Concept

This document is the source of truth for the product and research idea behind
Traj-Eval. It captures the problem, the primary audience, and the intended
solution. The concept is broader than the current implementation, so the final
section records the project state as of July 23, 2026.

## The idea in one sentence

Traj-Eval is a trajectory-evaluation harness that helps research teams
evaluating multi-agent AI for scientific and formal reasoning understand which
workflows they can trust, where they break down, and which changes actually
improve reliability by examining how the agents worked together and checking
their work against independent evidence, rather than judging only the final
answer.

## 1. The problem

### Scientific-agent results can look correct without being trustworthy

Research teams are increasingly using AI agents for scientific work such as
planning analyses, writing and running code, calling specialist tools,
interpreting results, and constructing formal proofs. In a multi-agent
workflow, this work is divided between three reasoning roles: a Reasoner, an
Engineer or formaliser, and a Critic or reviewer. A non-agent computer/runtime
mechanically executes the tools and code requested by those agents.

Most evaluations reduce the whole process to a final score: whether a proof
compiled, code ran, a statistical threshold was met, or an answer looked
plausible. That score can say whether the final submission passed a chosen
test, but it cannot reliably say whether the reasoning process was sound.

This creates a serious reliability gap. A system can produce:

- a statistically acceptable scientific result that violates physical
  constraints;
- a formally valid proof of a different statement from the one requested;
- working code that computes the wrong quantity;
- a plausible conclusion built on an earlier error;
- an answer approved by a critic who did not independently check it.

These are silent failures: the output looks successful under an incomplete
final check while something important in the path to that output is wrong.

### The root cause is that the work is distributed across a trajectory

Multi-agent scientific reasoning does not happen in one response. It unfolds
through a sequence of plans, messages, tool calls, intermediate calculations,
proof attempts, reviews, retries, and handoffs.

Responsibility is therefore distributed. A Reasoner may introduce a flawed
strategy, an Engineer may implement it faithfully, and a Critic may accept the
result. The non-agent runtime may then faithfully produce a clean-looking
artifact from those flawed instructions. By the time the problem appears in
the final output, it may be difficult to tell where it started or why the
reasoning agents did not catch it.

Multi-agent workflows also create failure modes that final-output evaluation
cannot see clearly:

- agents can pass work forward without meaningful repair;
- one agent's error can propagate through the rest of the team;
- repeated attempts can reproduce the same mistake rather than make progress;
- agents can change the task or scientific claim while appearing productive;
- a critic can mask a failure by approving work on trust;
- agents can report high confidence despite evidence that their work is wrong;
- parallel or specialised agents can add coordination cost without adding
  reliability.

The problem becomes harder because scientific domains differ in how much of
the intermediate work can be checked. Lean theorem proving is fully
step-verifiable through the kernel and proof state. Astrophysical inference is
only partially step-verifiable: intermediate values and final fits can be
recomputed, but a statistically plausible result may still recover the wrong
physical system. A meaningful evaluation must respect this difference rather
than treat all tasks as ordinary pass/fail benchmarks.

### Why current approaches fall short

Final success rates and aggregate benchmark scores are useful summaries, but
they collapse different kinds of behavior into the same outcome. Two systems
can have the same pass rate even if one catches and repairs errors while the
other silently approves invalid work.

Raw logs preserve more detail, but they place the burden on a human to
reconstruct what happened. As the number of tasks, trials, agents, models, and
configurations grows, manual review becomes slow, inconsistent, and difficult
to reproduce.

Generic observability tools show messages and tool calls, but activity is not
the same as scientific evidence. A timeline does not establish that an
intermediate claim, calculation, or proof state was correct.

Manual failure analysis can reveal important patterns, but it does not scale
well enough for repeated, controlled comparisons. Single-agent benchmarks also
miss failures caused by division of responsibility, handoffs, critic behavior,
and cross-agent error propagation.

An LLM judge may help a reviewer interpret a large amount of text, but its
opinion cannot replace physical validation, formal verification, or expert
review. Making another model the final authority would add a new opaque layer
to the same trust problem.

A dashboard can make evidence easier to inspect, but visualization alone does
not make the underlying evaluation valid. Showing more logs or metrics without
connecting them to independently checkable evidence merely moves the analysis
burden to the reviewer.

### Why the problem matters

Without a better way to evaluate the process, research teams can:

- accept scientifically wrong outputs because they are plausible or satisfy
  incomplete criteria;
- make weak claims that one model, role structure, or agent architecture is
  better than another;
- confuse more activity, more retries, or more agents with better reasoning;
- spend time and compute rerunning experiments without knowing what actually
  failed;
- repair the final answer while leaving the originating workflow problem
  unchanged;
- rely on critics or parallel agents that conceal or redistribute errors;
- produce findings that collaborators and reviewers cannot audit or
  reproduce;
- limit studies to a small number of manually inspected trials, weakening the
  evidence behind their conclusions.

The core problem is therefore not a lack of logs or metrics. It is the lack of
scalable, comparable, and scientifically grounded evidence that lets a human
decide whether a multi-agent reasoning process deserves to be trusted.

## 2. The target audience

### Primary target segment

The initial target is **academic AI-evaluation teams benchmarking multi-agent
scientific reasoning in domains with verifiable intermediate steps**.

These teams are the strongest fit because they:

- already compare agent roles, models, tools, grounding strategies, and
  orchestration choices;
- run enough repeated trials for manual log review to become a real
  bottleneck;
- need to defend research claims, not merely demonstrate that an agent can
  finish a task;
- work with domain experts or external checks that can establish whether
  intermediate and final work is correct;
- are likely to adopt an early research-oriented harness and provide detailed
  feedback about its scientific validity.

The people using or reviewing the evidence include:

- researchers studying AI agents and multi-agent systems;
- engineers building agent workflows and controlled evaluations;
- computational scientists using agents in domains such as astrophysics;
- formal-methods researchers evaluating theorem-proving agents;
- benchmark designers defining tasks, comparisons, and correctness criteria;
- domain experts, supervisors, and research leads who decide whether the
  evidence supports a scientific claim.

The primary user is not simply someone who wants an agent to complete a task.
It is someone responsible for determining whether the process and result are
reliable enough to support a research conclusion.

### Initial validation context

Lean theorem proving and STARGAZER-style astrophysical inference are the
initial validation contexts, not the entire future audience.

Lean provides a strong starting point because correctness is mechanically
checkable at each proof step. It makes it possible to build and test the
evaluation method against firm external evidence.

Astrophysical inference provides the more difficult and scientifically central
case because intermediate reasoning is only partly checkable and wrong results
can still look statistically plausible. It tests whether the approach remains
useful when verification is incomplete and domain-specific.

The broader beachhead is research teams evaluating multi-agent systems in any
scientific or formal domain where at least some important intermediate claims
can be checked against evidence outside the agents themselves.

## 3. The solution

### Solution statement

**Traj-Eval is a trajectory-evaluation harness that helps research teams
evaluating multi-agent AI for scientific and formal reasoning know which
workflows they can trust, where they break down, and which changes actually
improve reliability by studying how the agents worked together and checking
their work against independent evidence, not just scoring the final answer.**

### Core value

Traj-Eval turns an experimental run from a final score into evidence about how
the work was done.

It allows a research team to distinguish between:

- a workflow that reaches a correct answer through a sound process;
- a workflow that makes an error, detects it, and repairs it;
- a workflow that fails visibly and can be diagnosed;
- a workflow that produces a plausible but invalid result;
- a workflow that succeeds only because the evaluation checked the wrong
  thing.

This makes comparisons between agent configurations more meaningful. Instead
of asking only whether one model, tool set, role structure, or parallel setup
has a higher pass rate, the team can ask what changed in the reasoning process,
which failure modes became more or less common, where failures first appeared,
and whether the apparent improvement is supported by independent checks.

The intended outcome is a defensible answer to three questions:

1. Which multi-agent workflows can we trust under the tested conditions?
2. When they fail, where does the failure begin and how does it spread?
3. Which controlled changes genuinely improve reliability rather than merely
   changing the final score?

### The approach in plain language

Each run is treated as a process that can be studied, not just an answer that
can be scored. The agents' work is recorded without changing how they behave.
Correctness is judged separately, using evidence appropriate to the domain.
For Lean, that evidence comes from the kernel, proof state, proof closure, and
the absence of shortcuts such as `sorry` or `admit`. For astrophysical
inference, it comes from recomputed scientific quantities, physical
constraints, fit quality, and recovery of the underlying system.

The recorded process and the independent checks are then considered together.
This makes it possible to identify the first point at which the work stopped
being supported by evidence, connect that point to the responsible event or
agent, and see how the mistake affected later work.

Repeated experiments can then compare roles, models, tools, grounding,
workflow rules, and parallel-agent arrangements on matched tasks and budgets.
The comparison is not considered valid merely because one configuration
produced more passing outputs. It must show how the process and failure
patterns changed under a fair comparison.

The evidence should eventually scale from machine-readable results to a
focused human review. Automated measurements and an optional model-based
second opinion can help organise and prioritise the material, but neither
replaces independently checkable evidence or the final judgment of a qualified
human reviewer.

The intended evidence flow is:

```text
task
-> agent run
-> recorded collaboration
-> independent scientific or formal checks
-> first failure and propagation analysis
-> matched comparison
-> human review
```

### What makes the approach worth it

The differentiator is not simply that Traj-Eval stores more logs. It connects
the way agents collaborated to evidence that exists outside their own
statements.

This matters because the most dangerous scientific-agent failures are often
the ones that look convincing. A changed theorem can compile. A wrong physical
model can fit the observations. A critic can confidently approve work it did
not verify. Traj-Eval is valuable when it exposes the difference between a
successful-looking run and a trustworthy one.

The separation between recording and judging also means an old run can be
re-examined when the research team develops a new failure hypothesis or a
better correctness check. The agents do not have to be rerun merely because
the evaluation question changed.

The common part of the approach should transfer between domains: recording the
collaboration, preserving causal order, and comparing workflows fairly. The
definition of correctness must remain domain-specific. This keeps the concept
broad enough to be useful without making the unsupported claim that one set of
scientific checks works everywhere.

### What Traj-Eval is not

Traj-Eval is not an attempt to build a new foundation model. It evaluates
agentic scientific workflows and the factors that affect their reliability.

It is not a generic logging product whose success is measured by how many
events it stores.

It is not a dashboard that treats visibility as proof of interpretability.

It is not an LLM judge that replaces formal checks, scientific validation, or
human expertise.

It does not claim to explain the internal model-level cause of every failure.
Its nearer-term goal is to localise failures to observable events and agents,
classify recurring workflow patterns, and test whether those patterns change
under controlled conditions.

It also does not claim that one architecture is superior until matched
experiments provide evidence for that conclusion.

## Current project position

The following is implementation context as of **July 23, 2026**. It records
what currently supports the concept and what remains planned; it should not be
confused with the enduring product definition above.

### What exists now

The Lean side runs end to end. The project can record the work of a
Reasoner-Engineer-Critic team, allow the agents to use Lean proof tools, store
the run as structured evidence, and independently verify the submitted proof.
The recording layer is intended to observe the agents without changing their
behavior, while correctness is assessed afterwards.

The current benchmark contains 30 Lean tasks. The reported experiment set
includes:

- 100 easy runs across 10 tasks, with 56 independently verified final proofs;
- 20 medium runs across 2 tasks, with no independently verified final proof.

The easy and medium cohorts are not a controlled architecture comparison
because task difficulty and orchestration changed together. They cannot yet
support a claim that one workflow design is better than another.

The recorded easy runs already demonstrate why trajectory-level evaluation
matters:

- 97 of 100 traces were connected but forward-only, with no backward repair
  handoff from Engineer to Reasoner or Critic to Engineer;
- 12 of 100 runs showed sustained repeated search, and 11 of those remained
  unsolved;
- 5 of 100 Engineers changed the requested theorem, producing 4 silent
  failures;
- 30 of 59 accepted submissions were approved without a Critic proof-check
  call.

These observations identify workflow mechanisms worth testing. They do not yet
establish that a particular agent architecture, model, or tool configuration
is superior.

### What remains to be demonstrated

The next stage is to run matched comparisons in which tasks and budgets remain
the same while roles, models, tools, workflow rules, or parallel agents are
changed deliberately.

The evidence-review path must also be scaled so that machine-readable
measurements lead to focused human audit across cohorts without turning an LLM
judge or dashboard into the source of truth.

The STARGAZER astrophysics transfer has not yet been completed. Until a second
domain works end to end, reuse beyond Lean is a design intention rather than a
demonstrated result.

Early-warning claims also remain a research goal. The project must still test
whether trajectory signals degrade before final pass rates fall under
increasingly difficult or incomplete conditions.

## Durable concept boundary

The enduring idea is:

> Evaluate scientific AI agents as research objects by connecting their
> collaboration trajectory to independent evidence, so humans can compare
> workflows, diagnose silent failures, and make defensible claims about
> reliability.

Lean is the current fully verifiable testbed. STARGAZER is the planned
partially verifiable scientific testbed. The long-term value is not tied to one
agent framework, model, or benchmark, but every new domain must supply its own
credible definition of correctness.
