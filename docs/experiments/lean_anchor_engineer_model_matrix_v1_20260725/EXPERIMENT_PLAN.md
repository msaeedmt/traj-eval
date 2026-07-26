# Lean-Anchor Engineer Model Matrix

## Status

- Experiment ID: `lean-anchor-engineer-model-matrix-v1`
- Planning date: 2026-07-25
- Execution branch: `han-lean-anchors-merge`
- Baseline commit: `3f3897c72c441f8286f0d437475e5cbcd3d10040`
- Runtime commit: `7ebd9bda28dd3463421a2268e279961940444e78`
- Current state: **ready for the user-authorized notebook-route provider probe**
- Active models: two pinned OpenAI models and two pinned Mistral models
- Qwen policy: **historical evidence only; no new Qwen model or provider call**

This document pre-registers a model matrix for the integrated Lean-Anchor
Engineer. It is an experiment plan, not a result. Smoke completion, artifact
creation, or provider reachability must not be reported as scientific success.

## Scientific purpose

The fixed object of study is the Lean-Anchor Reasoner–Engineer–Critic workflow.
The experiment changes only the model assigned to each reasoning role.

The experiment supports:

- **O1 localisation:** identify the first failed Lean anchor and originating
  role/event;
- **O2 failure taxonomy:** distinguish strategy, formalisation, review,
  provider, trace, and validation failures;
- **O3 matched comparison:** compare A1 with B1 while holding Reasoner,
  Engineer, tasks, budgets, tools, and verification constant and changing only
  the Critic model.

The homogeneous A1–A4 matrix is exploratory model evidence. It is not an
architecture comparison. The STARGAZER warehouse is used only for operational
warnings and claim discipline, not as a Lean model ranking.

## Fixed Engineer implementation

The experiment tests the integrated Merge-branch form of the teammate's
Lean-Anchor Engineer:

| Field | Required value |
| --- | --- |
| Setup | `recovery_triangle_v1` |
| Source | `src/traj_eval/agents/roles.py` |
| Factory | `make_engineer_free` |
| Prompt constant | `ENGINEER_FREE_SYSTEM_MESSAGE` |
| `roles.py` Git blob | `3c86b475e6b1d80c1e15fa207ef27188c96f45fb` |

The run must fail closed if this identity changes. The following paths or
factories are not part of the selected trial path and must not be invoked:

- `src/traj_eval/agents/engineer/`
- `scripts/run_agent_runtime.py`
- `make_engineer_subgoals`

The model called the *Engineer model* may change by arm, but the Engineer
factory, prompt, tools, task input, and correctness gate remain fixed.

`traj_eval.agents.subgoal_state` is absent from this Merge runtime and is not
imported by the selected `recovery_triangle_v1` runner path. The fixed tool
surface includes `show_goals`; it is not a subgoal-agent implementation.

## OpenAI and Mistral model matrix

| Arm | Reasoner | Engineer | Critic | Purpose |
| --- | --- | --- | --- | --- |
| A1 | `openai/gpt-5.4-2026-03-05` | `openai/gpt-5.4-2026-03-05` | `openai/gpt-5.4-2026-03-05` | Quality-first OpenAI homogeneous baseline |
| A2 | `openai/gpt-5.4-mini-2026-03-17` | `openai/gpt-5.4-mini-2026-03-17` | `openai/gpt-5.4-mini-2026-03-17` | OpenAI scaling comparator |
| A3 | `mistral/codestral-2508` | `mistral/codestral-2508` | `mistral/codestral-2508` | Mistral code-generation comparator |
| A4 | `mistral/devstral-2512` | `mistral/devstral-2512` | `mistral/devstral-2512` | Mistral software-engineering comparator |
| B1 | `openai/gpt-5.4-2026-03-05` | `openai/gpt-5.4-2026-03-05` | `mistral/codestral-2508` | Matched Critic ablation against A1 |

No Qwen ID may be inserted into the model table, an arm, a fallback, or a
provider request. A missing OpenAI or Mistral route blocks the affected arm;
there is no silent model substitution.

## Provider transport gate (user-authorized notebook route)

On 2026-07-25, non-secret inspection found that the existing notebook-tested
OpenAI-compatible route uses plaintext `http` to a non-loopback host. The host,
path, full URL, credentials, response text, and provider error bodies are not
recorded here or in Git.

The user explicitly authorized this experiment to use the API configuration
already tested in `notebooks/OpenAI_config_test.ipynb`. Configuration `v003`
records this bounded route exception without recording the destination or
credential. It applies only to the pinned OpenAI and Mistral model probes and
experiment arms; it does not authorize Qwen calls, catalogue probes, or model
substitution.

Before each run, the provider gate sends one minimal request per model required
by that run: 30-second timeout, eight output tokens, temperature zero, and zero
client retries. `provider_probe.json` records only model ID, status, latency,
sanitized error class/status, route alias, transport scheme, and probe settings.
A failed probe ends that run ID before Trial 1.

The Runtime commit fixes AG2 provider retries at zero. Normal credential and
route secrecy remains mandatory despite the explicitly authorized transport
exception.

## Complete Easy and Medium cohort

The experiment covers every Easy and Medium problem currently registered in
`dataset/Lean/metadata.json`: 10 Easy and 10 Medium problems.

Dataset provenance:

- MiniFATELeanCat Git tree:
  `97833bd7a6c8d4835a0b7ff44d78d90257913501`
- metadata Git blob:
  `4ae6f1bfeb3cc3fcf62315f7c2d85ba5233c0125`
- metadata SHA-256:
  `89e01461a209abae3025d0bee485af240ca15c2977e5d43eac0ca6f14291be18`

### Easy tasks

1. `easy_fatem_011`
2. `easy_fatem_012`
3. `easy_fatem_019`
4. `easy_fatem_020`
5. `easy_fatem_041`
6. `easy_fatem_109`
7. `easy_fatem_111`
8. `easy_fatem_115`
9. `easy_leancat_001`
10. `easy_leancat_002`

### Medium tasks

1. `medium_fateh_001`
2. `medium_fateh_002`
3. `medium_fateh_009`
4. `medium_fateh_010`
5. `medium_fateh_011`
6. `medium_fateh_012`
7. `medium_fateh_013`
8. `medium_fateh_097`
9. `medium_leancat_008`
10. `medium_leancat_021`

Changing this set after outcomes are inspected requires a new configuration
version and an explicit explanation.

## Trial schedule

All roles use temperature `0.2`, 30 routing turns, and the following output
budgets:

| Role | Maximum output tokens |
| --- | ---: |
| Reasoner | 2,048 |
| Engineer | 4,096 |
| Critic | 2,048 |

The worker timeout is 180 seconds and the Lean timeout is 360 seconds. The
external probe has zero client retries. Runtime commit `7ebd9bda28dd3463421a2268e279961940444e78` fixes the effective AG2 provider-retry setting at zero. Arm order is blocked by task and repeat, then shuffled using seed
`20260725`.

| Phase | Arms | Tasks | Repetitions | Scheduled trials | Claim level |
| --- | --- | ---: | ---: | ---: | --- |
| Smoke | A1–A4, B1 | `easy_leancat_001`, `medium_leancat_008` | 1 | 10 | Technical smoke only |
| All-task pilot | A1–A4, B1 | all 20 Easy/Medium tasks | 3 | 300 | Exploratory model matrix |
| Paired confirmation | A1, B1 | all 20 Easy/Medium tasks | 10 | 400 | Matched Critic ablation |
| **Total** |  |  |  | **710** |  |

Smoke proof failure does not by itself block the pilot. A provider, trace,
identity, dataset, or independent-validation failure does block the affected
arm until a new run ID is pre-registered.

## Historical Qwen evidence: preserve, never rerun

Existing Qwen evidence is protected baseline evidence and is not an output
target for this experiment.

### Merge-branch Easy baseline

- Path: `data/batch/version_1_trial_traces`
- Contents: 100 historical Qwen trials plus one README
- Git tree: `0fe3a0b0ca4ec83c08d7211c10f495420d3ccf77`
- Policy: read-only; never overwrite, rename, move, reuse, or append

### Han Medium baseline

The following 22 tracked artifacts remain referenced on
`Han@93988c80fb8984db2e609416249231a896e04bf5`:

| Path | Git tree |
| --- | --- |
| `data/batch/qwen_medium_subgoals_v1` | `a41a0ad91511c819809cb2702c1ea51ba48af922` |
| `data/analysis/qwen_medium_subgoals_v1` | `aaaad4aedac63ae4b853306fbe76944a7b1de67a` |
| `docs/experiments/qwen_medium_subgoals_v1` | `72976ad8083ce81173326600b0f09eced57c6c2f` |

These Han artifacts are not copied into the Merge branch by this experiment.
Any later import requires separate path-level approval and a new provenance
record.

Preflight must prove:

1. no configured arm contains `qwen`;
2. no provider request selects a Qwen model;
3. new output roots do not overlap a protected Qwen path;
4. protected Git trees remain unchanged after the experiment.

## Prior evidence that shapes this design

Previous Lean runs showed:

- 56 solved, 40 unsolved, and four silent failures in the historical Easy
  cohort;
- zero solved trials in the 20-trial Medium subgoal cohort;
- successful compiler probes and accepted subgoals without a completed proof;
- statement drift and wrong-target compilation;
- API/identifier hallucinations, typeclass failures, repeated searches, and
  repair loops;
- Critic decisions that did not always imply independent proof verification;
- one model-screen batch lost to Windows console encoding before responses were
  persisted.

The current warehouse adds operational warnings for format fragility,
premature convergence, perseveration, reasoning loops, environment/tool
failure, provider timeouts, and critic masking. These are preflight and
taxonomy inputs only; the warehouse's STARGAZER architecture ranking is not
evidence that an OpenAI or Mistral model is better at Lean.

Consequently, responses and trace events must be written incrementally in
UTF-8, and provider/tooling-invalid runs must never be counted as reasoning
failures.

## Correctness and failure gates

A trial is `solved` only when independent validation establishes all of:

- kernel verification;
- closed proof;
- exact statement preservation;
- no `sorry`;
- no `admit`;
- no added axiom;
- axiom-clean result.

Mutually exclusive top-level outcomes are:

- `solved`
- `unsolved`
- `silent_failure`
- `provider_invalid`
- `trace_invalid`
- `artifact_invalid`
- `validation_unknown`

Failure analysis records the first decisive failed event, first violated Lean
anchor, originating role, compiler evidence, downstream propagation, and
whether the Critic independently checked the exact final proof.

## Analysis

Easy and Medium results remain separate. Required metrics include:

- scheduled, started, terminal, trace-valid, and independently validated counts;
- kernel-verified proof rate and confidence interval;
- pass@1 and, where 10 repetitions exist, pass@5;
- Critic check coverage and accept-without-check count;
- tool-use efficiency, retry rate, retry-success rate, and repeated-probe rate;
- first violated anchor and error-localisation depth;
- longest path and dead-end fraction;
- silent failure, statement drift, and wrong-target counts.

A1/B1 is paired by task and repetition. The confirmatory analysis uses exact
McNemar for paired binary outcomes, 10,000 paired-bootstrap resamples,
Bonferroni correction by metric family, and effect sizes. A1–A4 pilot
comparisons remain exploratory.

## IDs and isolated output layout

- Run ID: `lae-mm-v1_<phase>_<arm>_<YYYYMMDDTHHMMSSZ>`
- Trial ID: `<run-id>__<task-id>__tNN`
- Machine time: UTC
- Human-readable local time: Europe/Berlin, recorded separately

```text
data/batch/lean_anchor_engineer_model_matrix_v1/<run-id>/
├── run_manifest.json
├── provider_probe.json
├── traces/<arm>/<trial-id>.jsonl
├── logs/
└── COMPLETED.md or FAILED.md

data/analysis/lean_anchor_engineer_model_matrix_v1/<run-id>/
├── summary.json
├── metrics.json
└── failure_labels.jsonl

docs/experiments/lean_anchor_engineer_model_matrix_v1_20260725/<run-id>/
└── RESULTS.md
```

No generic `latest` directory or reusable output filename is allowed. Existing
files cause a fail-closed collision error. Infrastructure retries receive a
new attempt ID; agent failures are not retried outside scheduled repetitions.

## Run materialisation protocol

For each phase/arm invocation, the operator performs the following sequence in
order. It is deliberately separate from the agent runtime so that a failed
provider probe cannot be mistaken for a Lean trial.

1. Allocate one fresh UTC run ID and confirm that neither its raw nor analysis
   root exists.
2. Verify the frozen branch, runtime commit, Engineer blob, MiniFATELeanCat
   tree, metadata hash, selected task IDs, and protected Qwen trees.
3. Run the user-authorized notebook-route, non-secret provider probe described
   above. A failed probe ends that run ID; it is never overwritten or reused.
4. Materialise `run_manifest.json` from
   `config/run_manifest.template.v003.json`, populate the exact command argv,
   arm models, task IDs, config/probe SHA-256 values, preflight facts, and
   paths, then freeze it before Trial 1.
5. Invoke `scripts/run_batch.py` with explicit `--reasoner-model`,
   `--engineer-model`, `--critic-model`, role-specific token budgets,
   `--run-id`, and the phase's pre-registered `--task-id` list, plus the
   arm's trace directory and a distinct analysis directory. The task list is
   passed explicitly rather than inferred from filesystem/loader order.
   `--worker-model` is only the compatible homogeneous fallback and is not
   used to select a hidden model.
6. Preserve every JSONL trace and summary. Label incomplete, provider, trace,
   artefact, and validation failures separately; do not re-run an agent error
   outside its scheduled repetition.

The wrapper computes the seed-`20260725` arm order and stores the resulting
order in each manifest. The configuration's Easy and Medium lists are the
authoritative task order; the loader's equivalent set may enumerate them in a
different order.

The current runner records the role models and rejects an existing trace file.
The manifest and derived `metrics.json`/`failure_labels.jsonl` are operational
artifacts to be materialised by the documented wrapper process before analysis;
their absence blocks phase completion rather than allowing an informal result.

## Configuration ledger

| Artifact | ID | SHA-256 | Status |
| --- | --- | --- | --- |
| `config/experiment_config.v001.json` | `lae-mm-v1-config-v001` | `6f38ac6a4d2e7765cc97fffaa2d6a8c845803c1acd7addb5b82414e769bf57d6` | Draft; blocked |
| `config/run_manifest.template.v001.json` | `lae-mm-v1-run-manifest-template-v001` | `2d3bd46981ccd1c72fd442a5c3550d236e16d5739afc15e303191e9582dd9ad9` | Template |
| `config/experiment_config.v002.json` | `lae-mm-v1-config-v002` | `ff1369a1cb177c763ac9b21f13801ab21f1ce53cd53eead35ad24dbaaeb035fb` | Active; HTTPS/provider-retry gate blocked |
| `config/run_manifest.template.v002.json` | `lae-mm-v1-run-manifest-template-v002` | `6b9056cf0658eab3b3640edf18464a400a948a5defcb3855d0cbe4c5dba28e33` | Active template |
| `config/experiment_config.v003.json` | `lae-mm-v1-config-v003` | `143818d6ffd29e0decdfe46c4af863df6f7f7203d9ad0fa9b7745bb08a0854dc` | Active; notebook route authorized, ready for probe |
| `config/run_manifest.template.v003.json` | `lae-mm-v1-run-manifest-template-v003` | `1882385ed7bdf667ca432101745001d91659b39981d131b748d5d2515b4b89f4` | Active template |

These files are immutable after approval. Any semantic change creates the next
numbered file and records `supersedes_config_id`; it does not overwrite v001.

## Version-control and handoff rule

The experiment executes in `han-lean-anchors-merge` as explicitly requested.
Under `CODEX.md`, this directory remains an untracked Merge-branch drafting
area: it is not committed there. After user review, the approved configuration,
manifest, summary, metrics, and failure-label JSON files are copied
byte-identically to their reviewed `Han` counterparts and committed/pushed
there with their recorded SHA-256 values. No existing artifact is overwritten,
moved, or renamed; every restart receives a new run ID.

Before staging any result artifact, verify that it contains no provider URL,
credential, provider error body, or local-only path. Raw JSONL traces remain
linked by exact run/trial ID and are committed only when the user approves
their size and content for the canonical branch. The protected historical Qwen
paths are never staged as part of this handoff.

## Resolved runner preflight

Runtime commit `7ebd9bda28dd3463421a2268e279961940444e78` resolved both v001 runner blockers and fixes the provider retry policy at zero:

1. `scripts/run_batch.py` now accepts explicit Reasoner, Engineer, and Critic
   model IDs and per-role token budgets while retaining `--worker-model` and
   `--worker-max-tokens` as compatible homogeneous fallbacks.
2. The faithful `recovery_triangle_v1` path no longer imports
   `traj_eval.agents.subgoal_state`. It exposes the fixed `check_lean`,
   `search_lemmas`, `try_tactic`, and `show_goals` surface. Selecting either
   excluded subgoal-agent setup fails before any provider request.

The runner records effective models in `TrialMeta.config.worker_models`, uses
`backbone: "mixed"` for B1, supports exact task selection and immutable run
IDs, and refuses to overwrite an existing trace.

Verification before freezing v002:

- 49 focused runner, configuration, and free-routing tests passed;
- three pre-existing filesystem tests were deselected because the managed
  sandbox denied pytest's global temporary directory;
- the B1 dry-run loaded all 20 Easy and Medium tasks with the registered
  2,048/4,096/2,048 role budgets;
- `import Mathlib` plus `example : True := by trivial` compiled sorry-free
  through the same local Lean CLI validator;
- `roles.py`, the dataset tree, metadata blob, and protected Qwen Easy tree
  retained their registered hashes.

The provider transport check has not yet been executed. Configuration v003
records the user's explicit authorization for the existing notebook-tested
HTTP route, while the runtime fixes AG2 provider retries at zero.

Versions v001 and v002 remain immutable audit records. Version v003 is the
active full snapshot.

## Start gate

Before Trial 1:

1. branch is exactly `han-lean-anchors-merge`;
2. the tracked worktree is clean before run outputs are created; the only
   permitted untracked pre-existing paths are the merge-branch experiment
   drafts under this document's directory;
3. Engineer blob and import-path gates pass;
4. all 20 task IDs load from the pinned metadata;
5. the selected OpenAI and Mistral models pass the user-authorized notebook-route,
   non-secret provider probes with zero client and AG2 retries;
6. no Qwen provider call is configured;
7. configuration and manifest hashes match this ledger;
8. output collision and protected-evidence checks pass;
9. independent Lean validation is enabled;
10. the frozen `run_manifest.json` is written before the first trial.

Until all ten checks pass, status remains `not_run`, and no scientific claim is
permitted.
