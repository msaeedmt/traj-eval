# Critic Review Entry Point

task_id: stargazer_real_001_qwen_true_task
trial_id: engineer-stargazer_real_001_qwen_true_task-813c2313

Read files from disk. Do not extract source from engineer chat.

Start here:

- `run_manifest.json`
- `events.jsonl`
- `after_status.txt`
- `after_diff.patch`
- `changed_files.json`
- `changed_snapshots/`
- `private_artifacts` in `run_manifest.json` for ignored generated outputs

Version rule:

- Same `task_id` plus a later timestamped run folder means a later engineer version.
- The critic compares `after_diff.patch`, `changed_files.json`, and `changed_snapshots/`, not prose.
