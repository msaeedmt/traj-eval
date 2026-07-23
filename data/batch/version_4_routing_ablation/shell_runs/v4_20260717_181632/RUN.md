# Han V4 Routing Ablation Run

- Run ID: v4_20260717_181632
- Started: 2026-07-17T18:16:33.1844970+02:00
- Git branch: Han-experiment
- Git commit: 41cc85f3cc87aa99c9ba81eb345d0ee0f15f69fa
- Stage selection: smoke
- Model: openai/Qwen3.5-27B-Q5_K_M.gguf
- Tasks: easy_fatem_019, easy_fatem_020
- Arms: legacy_deterministic, upstream_free, central_worker_matched, central_total_call_matched
- Official trials per task and arm: 20
- Worker-turn cap: 200
- Total-call cap for the matched central arm: 200
- Worker timeout seconds: 180
- Provider-internal retries: 0
- Recorded outer infrastructure retries: at most 1 per slot
- Retrieval-only no-progress threshold: 8 completed Reasoner search_lemmas calls, evaluated after each executor batch; a parallel batch may cross the threshold and is counted exactly
- Conservative maximum model calls: 4002
- Lean project: `dataset/Lean`
- Provider configuration: `<local-provider-config>` (credentials not copied)

## Output layout

- logs/: one console log per executed stage
- smoke/controller_stuck/: planner and Engineer stuck-routing probes
- smoke/arm_smoke/: one matched trial per task and arm
- <arm>/: official JSONL traces, summary.json, and RESULTS.md
- analysis/: paired statistics and COMPARISON.md
- run_manifest.json: machine-readable official-run manifest
- COMPLETED.md or FAILED.md: terminal launcher status

## Claim boundary

This run was produced at commit `41cc85f` before the later local
stall-handoff implementation. It is baseline routing-ablation evidence, not
validation of `recovery_triangle_stall_handoff_v1`.

This two-task, one-model experiment can identify routing burden, safety defects, and a promising recovery effect. It cannot establish overall NLP-proposal improvement without broader repeated tasks and a single-agent control.
