# CODEX.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## Project-specific guidance

### Product

Traj-Eval is a trajectory-evaluation harness for academic AI-evaluation teams
studying multi-agent scientific reasoning. It connects recorded collaboration
to independent scientific or formal checks so teams can determine which
workflows are trustworthy, where failures begin, and which changes improve
reliability.

`docs/idea/concept.md` is the source of truth for the product definition and
status. `README.md` is the implementation entry point.

### Model

- The reasoning agents are **Reasoner**, **Engineer**, and **Critic**.
- Tool execution is not an agent role. A non-agent computer/runtime executes
  tools and code; reasoning agents perform revisions.
- Treat legacy references to a Planner, Executor/Repairer, or four-agent
  configuration as historical. New work uses only the three reasoning agents
  above unless the user explicitly changes the model.
- Recording must not change agent behavior. Correctness is evaluated
  separately.
- Lean is the current fully verifiable testbed. STARGAZER is planned and
  partially verifiable. Correctness checks remain domain-specific.

### Conventions

- A passing run, test, artifact, or dashboard is not a scientific result.
  Claims need recorded trajectory evidence, independent checks, matched tasks
  and budgets, and qualified human review.
- Label claims as implemented, observed, partially supported, or planned.
  Treat structural signals such as retries and cycles as hypotheses until
  validated.
- Keep `CODEX.md` at the repository root. Put all other project documentation
  in `docs/`; keep the product concept at `docs/idea/concept.md`.
- Put raw traces in `data/batch/` and reproducible derived data in
  `data/analysis/`.
- Update schemas, tests, and documentation together when a trace contract,
  detector label, or metric meaning changes.
- Keep private Science-Work-Flow paths, local provider settings, secrets, raw
  archives, and bulky outputs out of this public repository.


## Standards

- Never modify the `lean-anchors` branch. It belongs to a teammate.
- Keep experiments and work-in-progress changes on the `Han` branch.
- Use `han-lean-anchors-merge` only for gated changes promoted from `Han`
  after the user has discussed them with teammates and explicitly approved
  the promotion.
- Documentation exception: `docs/` in the merge worktree is an untracked
  drafting area. Draft or revise documentation there when useful, then copy it
  to the corresponding `Han` path for review, commit, and push. Never commit
  documentation changes on the merge branch.
