# Han-Lean-Anchor Merge

This note records the merge technique and the architecture rule for combining
`Han` with `lean-anchors`.

## Branch Meaning

- `Han` owns the Engineer, Qwen, Stargazer, and public Lean dataset work.
- `lean-anchors` owns Lean tools, Lean validation, Lean metrics, and routing experiments.
- `han-lean-anchors-merge` is the integration branch.
- Do not rewrite `Han`.
- Do not rewrite `lean-anchors`.
- Use this branch to combine and repair the two lines of work.

## Merge Technique

The normal merge failed on Windows.

The reason was not a code conflict.

The reason was invalid Windows paths from downloaded-file metadata:

```text
*:Zone.Identifier
```

Those paths exist in `origin/lean-anchors`.

Windows cannot check them out as normal files.

The integration branch was created from `Han`:

```powershell
git switch Han
git switch -c han-lean-anchors-merge
```

Then the valid `lean-anchors` files were copied in:

```powershell
git fetch origin lean-anchors
git checkout origin/lean-anchors -- . ":(exclude,glob)**/*:Zone.Identifier"
```

Then the result was committed:

```text
e491473 Integrate lean anchors into Han branch
```

This is a Windows-clean integration snapshot.

It is not a full Git merge commit.

That is intentional.

## Authority Rule

AG2 owns agent conversation.

The runtime owns authority.

Lean/compiler/test evidence owns truth.

JSON memory must be typed evidence.

Trace JSONL records the trajectory.

An agent claim is not enough.

A step is done only when deterministic checks pass.

## Minimal Runtime Shape

Use AG2 for roles:

- Planner
- Engineer
- Critic
- Executor

Use deterministic gates for completion:

- allowed files only
- compiler passes
- no new `sorry`
- no forbidden Lean shortcuts
- tests or validators pass
- planner accepts after evidence

The important check is:

```text
planner_accepts and verifier_passes
```

Not:

```text
planner_accepts
```

## Reuse Rule

Do not build a new Lean verifier from scratch.

Reuse from `lean-anchors`:

- Lean compiler tool
- Lean search tool
- artifact extraction
- offline validator
- Lean metrics
- perseveration detector

Build only thin orchestration glue around them.

## YAGNI Rule

Do not add a general agent platform now.

Do not add a new session gateway now.

Do not add dashboards, MCP, SQLite, or parallel DAGs now.

First make one Lean task flow reliable:

```text
plan -> edit -> compile -> validate -> trace -> review
```

Then generalize only after the failure modes are visible.
