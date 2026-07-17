# Central Controller: Total-Call-Matched

This uses the same routing-only Qwen controller and stuck-recovery contract as
the worker-matched controller arm. The difference is budget accounting:
controller and worker calls share one maximum of 200 model calls.

This arm tests whether a controller still helps when its routing decisions
consume opportunity that would otherwise belong to a worker. It receives 20
trials for each selected task. `RESULTS.md` and `summary.json` are generated
only after completion and are never overwritten.
