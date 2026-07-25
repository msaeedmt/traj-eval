# Model Selection

## 1. API-confirmed chat candidates

### Scope and evidence boundary

This section records which catalogue entries were observed to work with the
current OpenAI-compatible endpoint through Traj-Eval's `chat.completions`
interface. It is an operational provider probe, not a Lean evaluation, a
scientific result, or evidence that a model is suitable for the final rerun.

The evidence is the local batch
`runs/provider_probes/chat_catalogue_20260724T183049437393Z.csv`, generated
on July 24, 2026. The probe parsed `docs/models/models.md`, removed two
wildcards and duplicate IDs, then sent one minimal chat-completions request to
each of 254 concrete catalogue entries. It used a 30-second request timeout
and at most three concurrent requests.

| Observed status | Count | Interpretation |
| --- | ---: | --- |
| `CHAT_COMPATIBLE` | 74 | The endpoint returned a chat completion for this model ID. |
| `CHAT_ERROR` | 180 | This model ID was not confirmed for this endpoint's chat-completions route. |

The successful list below is therefore the current pool of **API-usable chat
candidates**. A later selection still needs matched task, budget, prompt,
tool, trace, and independent Lean-verification decisions.

### Usable `mistral/` route candidates (28)

- `mistral/mistral-large-latest`
- `mistral/devstral-latest`
- `mistral/codestral-2508`
- `mistral/mistral-large-2512`
- `mistral/mistral-medium-2312`
- `mistral/magistral-small-latest`
- `mistral/mistral-large-2407`
- `mistral/magistral-medium-latest`
- `mistral/open-mistral-nemo-2407`
- `mistral/open-mixtral-8x22b`
- `mistral/labs-devstral-small-2512`
- `mistral/codestral-2405`
- `mistral/mistral-medium`
- `mistral/mistral-medium-latest`
- `mistral/open-mistral-7b`
- `mistral/mistral-small-latest`
- `mistral/open-mistral-nemo`
- `mistral/devstral-medium-latest`
- `mistral/mistral-small`
- `mistral/mistral-tiny`
- `mistral/devstral-2512`
- `mistral/magistral-medium-2509`
- `mistral/open-mixtral-8x7b`
- `mistral/devstral-small-latest`
- `mistral/mistral-large-2402`
- `mistral/pixtral-12b-2409`
- `mistral/mistral-medium-2505`
- `mistral/codestral-latest`

### Usable `openai/` route candidates (46)

- `openai/o3-2025-04-16`
- `openai/gpt-5-search-api`
- `openai/gpt-5.4-nano`
- `openai/gpt-5-2025-08-07`
- `openai/gpt-5-mini`
- `openai/o3-mini`
- `openai/gpt-4-turbo-2024-04-09`
- `openai/o3`
- `openai/gpt-4.1-nano`
- `openai/gpt-5.2-2025-12-11`
- `openai/gpt-5.4-nano-2026-03-17`
- `openai/gpt-4o-2024-08-06`
- `openai/gpt-4o-2024-05-13`
- `openai/gpt-5`
- `openai/gpt-5.2-chat-latest`
- `openai/gpt-4o`
- `openai/gpt-4-0613`
- `openai/o4-mini`
- `openai/gpt-5-search-api-2025-10-14`
- `openai/gpt-5-nano`
- `openai/gpt-5.4-mini`
- `openai/gpt-4`
- `openai/gpt-5.4-2026-03-05`
- `openai/gpt-4-turbo`
- `openai/o3-mini-2025-01-31`
- `openai/gpt-4.1-nano-2025-04-14`
- `openai/gpt-4.1-mini`
- `openai/o1-2024-12-17`
- `openai/o4-mini-2025-04-16`
- `openai/gpt-3.5-turbo-0125`
- `openai/gpt-3.5-turbo-1106`
- `openai/gpt-3.5-turbo-16k`
- `openai/gpt-4o-2024-11-20`
- `openai/gpt-5.3-chat-latest`
- `openai/gpt-4.1-2025-04-14`
- `openai/gpt-5-mini-2025-08-07`
- `openai/gpt-5-nano-2025-08-07`
- `openai/gpt-4o-mini-2024-07-18`
- `openai/gpt-5.2`
- `openai/gpt-5.4-mini-2026-03-17`
- `openai/gpt-4.1-mini-2025-04-14`
- `openai/gpt-4o-mini`
- `openai/gpt-5.4`
- `openai/gpt-4.1`
- `openai/gpt-3.5-turbo`
- `openai/o1`

### What the errors mean

The probe recorded 112 `BadRequestError`, 55 `NotFoundError`, 10
`InternalServerError`, two `PermissionDeniedError`, and one authentication
failure. Provider details were deliberately redacted, so these classes do not
identify a single cause per model.

Treat every `CHAT_ERROR` as **not currently confirmed for Traj-Eval's chat
route**, not as a general statement that the model is unavailable. Some
catalogue entries are intentionally for embeddings, images, audio, speech,
moderation, or realtime APIs; others may require a different route, a
different request contract, or different endpoint permissions. The one
authentication failure is endpoint/credential state, not model-quality
evidence.

Before choosing a model for the Lean rerun, repeat the probe for the intended
provider route and then compare only candidates with matched model settings,
tasks, budgets, tools, and independent kernel verification.

## 2. Lean task selection

### Purpose of the first task

The first Lean screen uses `leancat_s0001_id_comm` from
`dataset/Lean/MiniFATELeanCat/Easy/LeanCat001.lean`. It is an **Easy** task
with one theorem, one `sorry`, a small set of Mathlib category-theory imports,
and an unambiguous kernel pass/fail result.

That makes it useful for checking the complete path from API request to Lean
text extraction and independent compilation. It does **not** make it a useful
standalone benchmark. One easy theorem cannot estimate general math ability,
compare providers reliably, measure repair behavior, or predict performance on
the medium tasks planned for the main rerun.

The experiment is labeled **one-shot model-screening experiment**:

- one call per model in the replacement run;
- the same theorem source, prompt, temperature, 1,024-token output budget, and
  90-second timeout;
- no tools, compiler feedback, retries, or repair turns;
- three pinned OpenAI models and three pinned Mistral models;
- every emitted proof copied unchanged into
  `runs/provider_probes/model_test.lean`;
- success determined by Lean 4.30.0 with the pinned Mathlib v4.30.0
  environment, not by API completion or visual plausibility.

An initial blind six-call batch was discarded before any response was reviewed
because a Windows console-encoding error prevented the in-memory results from
being recorded. The table below is from the separately approved replacement
batch only. That instrumentation failure is retained in the run record rather
than hidden.

### Why these six usable models

The candidates were selected only from the 74 API-confirmed IDs in section 1.
Pinned IDs were preferred over `-latest` aliases.

| Candidate | Selection reason | Lifecycle caution |
| --- | --- | --- |
| `openai/gpt-5.4-2026-03-05` | Quality-first candidate. OpenAI describes GPT-5.4 as a frontier model for complex professional work with reasoning support. | A general coding/reasoning model, not a Lean-specialized model. |
| `openai/gpt-5.4-mini-2026-03-17` | Scaling candidate. OpenAI describes it as a faster, more efficient model for high-volume coding workloads. | Lower cost and latency do not imply Lean correctness. |
| `openai/o3-2025-04-16` | Math/science/coding reasoning comparator. | OpenAI says o3 has been succeeded by GPT-5. |
| `mistral/magistral-medium-2509` | Cross-provider reasoning comparator. | Mistral marks the native Magistral route as deprecated. |
| `mistral/devstral-2512` | Cross-provider software-engineering and code-agent comparator. | Mistral lists a May 22, 2026 deprecation date and a newer replacement. |
| `mistral/codestral-2508` | Cross-provider code-generation comparator. | Code generation is relevant but is not formal-proof specialization. |

Official documentation used for this selection:
[GPT-5.4](https://developers.openai.com/api/docs/models/gpt-5.4),
[GPT-5.4 mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini),
[o3](https://developers.openai.com/api/docs/models/o3),
[Mistral native-reasoning deprecation](https://docs.mistral.ai/resources/deprecated/native-reasoning),
[Devstral 2](https://docs.mistral.ai/models/model-cards/devstral-2-25-12),
and [Codestral 25.08](https://docs.mistral.ai/models/model-cards/codestral-25-08).

### One-shot result

| Model | API result | Lean candidate | Kernel result |
| --- | --- | --- | --- |
| `openai/gpt-5.4-2026-03-05` | Stopped normally | Yes | **Fail**: naturality proved a different proposition. |
| `openai/gpt-5.4-mini-2026-03-17` | Stopped normally | Yes | **Fail**: componentwise commutativity remained unsolved. |
| `openai/o3-2025-04-16` | Reached 1,024-token limit | No final proof | Not tested. |
| `mistral/magistral-medium-2509` | Reached 1,024-token limit | No final proof | Not tested. |
| `mistral/devstral-2512` | Stopped normally | Yes | **Fail**: invalid simp input, unknown identifier, and unsolved goal. |
| `mistral/codestral-2508` | Stopped normally | Yes | **Fail**: `rfl` did not prove the componentwise equation. |

The non-model reference control `exact NatTrans.id_comm α β` passed in the
same file and environment. The zero model passes are therefore proof failures,
not evidence that the task or Mathlib setup is broken.

There is no validated winner from this screen. For a next balanced pilot,
`openai/gpt-5.4-2026-03-05` remains the quality-first OpenAI candidate and
`mistral/codestral-2508` the current Mistral code-generation comparator, with
`openai/gpt-5.4-mini-2026-03-17` retained to measure the scaling tradeoff.
This is a priority for further testing, not a claim that any of the three is
Lean-capable.

The highest-domain-fit future candidate found in current documentation is
Mistral's
[`labs-leanstral-1-5`](https://docs.mistral.ai/models/model-cards/leanstral-1-5),
which is explicitly optimized for Lean 4 proof engineering. It is labeled
**future candidate—not tested** because it was absent from this endpoint's 74
confirmed usable chat IDs. Its route must pass the same compatibility probe
before it enters a matched evaluation.

### Tasks for the next evaluation

Do not scale from this single result directly. Pre-register a small,
stratified task set before the next API run:

- sample both Easy and Medium LeanCat tasks;
- keep the exact same task IDs across models and providers;
- exclude proof text, prior traces, and known solutions from prompts;
- separate pure one-shot generation from agentic runs that receive Lean
  feedback and repair opportunities;
- match output and tool budgets within each comparison;
- retain raw responses, normalized proof terms, compiler output, timing, and
  token use under `runs/provider_probes/`;
- report pass rate with task-level results and human-reviewed failure labels,
  rather than selecting a model from one anecdotal proof.
