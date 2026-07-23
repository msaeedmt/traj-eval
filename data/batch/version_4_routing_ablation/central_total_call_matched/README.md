# Central Controller: Total-Call-Matched

This uses the same routing-only Qwen controller and stuck-recovery contract as
the worker-matched controller arm. The difference is budget accounting:
controller and worker calls share one maximum of 200 model calls.

The pre-registered official design assigns 20 trials per selected task to this
arm; that official run has not been executed. Raw traces stay under this arm's
`data/batch/` directory, machine-readable summaries belong under
`data/analysis/version_4_routing_ablation/`, and reader-facing `RESULTS.md`
belongs under `docs/experiments/version_4_routing_ablation/`. Retained smoke
observations are descriptive only.
