# Stargazer True Task Engineer Evidence

This folder contains one public engineer-agent evidence bundle for Stargazer
`real_001`. It is not a placeholder run: Qwen wrote a fitting script that reads
the public observation arrays, detrends by instrument, searches candidate
periods with sinusoidal least squares, writes `agent_submission.json`, writes
`fit_diagnostics.json`, verifies the public parser returns one planet, runs
`git_status`, runs `git_diff`, and finishes.

Validate with:

```powershell
python -m pytest tests\engineer\test_stargazer_task.py --basetemp runs\pytest-temp -p no:cacheprovider
```
