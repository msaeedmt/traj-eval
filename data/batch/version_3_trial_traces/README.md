# Version 3 subgoal-DAG ablation traces

Version 3 tests the existing tool-routed subgoal DAG on the failed
`easy_fatem_019` theorem. The two named conditions share the same model,
theorem, controller, graph limits, 200-turn budget, Lean compiler, prompts and
validation gates.

The only intervention is the Engineer tool surface:

- `dag_only`: typed DAG tools, retrieval and compiler tools.
- `dag_plus_goal_tools`: the same surface plus `try_tactic` and `show_goals`.

Clean `t1` trials use Qwen thinking disabled, 1,500 output tokens per call and
a 180-second provider timeout. The runner records explicit terminal and
controller-plan events.

## Inventory and status

- `dag_only/easy_fatem_019_t0.jsonl`: pre-limit pilot, manually interrupted
  after a provider stall; 133 valid lines, 19 Lean checks, no terminal event.
- `dag_only/easy_fatem_019_t1.jsonl`: clean 200-turn arm; terminated at the
  turn cap, unsolved. It created/revised a graph, reached Engineer and made 25
  Lean checks (one successful probe, 24 failures), but never obtained critic
  acceptance.
- `dag_plus_goal_tools/easy_fatem_019_t1.jsonl`: matched combined arm;
  terminated `stuck` by the identical-call guard, unsolved. It made four Lean
  checks (one successful candidate, three failures), called `try_tactic` three
  times, reached candidate review, and never called `show_goals`.

The interrupted `t0` is retained as infrastructure evidence and is excluded
from the matched outcome comparison.
