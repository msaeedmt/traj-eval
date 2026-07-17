# Smoke Evidence

Smoke outputs are diagnostic gates and are excluded from all official success
rates.

- `controller_stuck/` receives exactly two routing-only Qwen probe results:
  one repeated Reasoner/planner stall and one strategic Engineer stall.
- `arm_smoke/` receives one full trial for each of two tasks and four arms.

Every target must be absent before its call starts. A failed or malformed smoke
artifact is retained and blocks the official run until the cause is understood.
