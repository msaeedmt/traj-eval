# Qwen + Saeed STARGAZER Clean Output

This folder is the readable handoff for the Qwen/Saeed STARGAZER run. It is intentionally curated: the raw per-iteration trace forest is not included here.

## Open First

- `figures/real_vs_agent_planet_visualization.png` - visual comparison of true and agent-proposed planet parameters.
- `evaluation/real_vs_agent_planet_parameters.csv` - table behind the figure.
- `evaluation/trajectory_evaluation_summary.json` - proposal-aligned trajectory-level evaluation summary.
- `evaluation/local_stargazer_benchmark.json` - separate STARGAZER benchmark result.
- `agent/clean_star_finding_summary.json` - compact agent workflow summary.
- `agent/approved_agent_submission.json` - final reviewer-approved agent submission from the workflow.

## Main Result

The agent workflow produced one submitted planet and the reviewer approved the result, but the separate STARGAZER benchmark did not pass.

Key benchmark values:

| Metric | Value |
| --- | --- |
| Scientific status | `scientific_fail` |
| Benchmark passed | `false` |
| Score | `0.6` |
| Match score | `0.022661` |
| RMS | `41.49204` |
| Failed components | `mass_amplitude`, `model_fit`, `period_recovery`, `phase_or_eccentricity` |

## Planet Comparison

| Quantity | Agent submission | Benchmark truth |
| --- | ---: | ---: |
| Period days | `2.868989` | `4.230785` |
| m sin i Mjup | `0.166203` | `0.461` |
| eccentricity | `0.0` | `0.013` |
| omega rad | `0.0` | `1.012291` |
| l rad | `4.748110` | `4.644516` |

## Interpretation

This run is useful as trajectory-level evidence: the workflow looked structurally valid and received reviewer approval, but output-level benchmark anchors later exposed a scientific failure. The important lesson is critic/reviewer masking: the reviewer accepted a result that failed hidden physical/model checks.

## Related Notebooks

The notebooks with visible cell outputs are in `notebooks/`:

- `notebooks/qwen_saeed_agent_stargazer.ipynb`
- `notebooks/qwen_saeed_stargazer_eval.ipynb`

Markdown exports are also available for quick reading:

- `notebooks/qwen_saeed_agent_stargazer.md`
- `notebooks/qwen_saeed_stargazer_eval.md`
