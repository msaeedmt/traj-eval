# Lean batch evidence

Each experiment configuration has exactly one folder. Inside a configuration
folder, trace files are flat and named `<problem>_tN.jsonl`. Phase is part of
the folder name so Pilot and Confirmation trials cannot collide.

## Lean Anchor engineer model matrix

| Configuration | Phase | Arm | Present | Missing |
|---|---:|---:|---:|---:|
| [smoke_A1_gpt54_all_roles](smoke_A1_gpt54_all_roles/) | smoke | A1 | 0/2 | 2 |
| [smoke_A2_gpt54mini_all_roles](smoke_A2_gpt54mini_all_roles/) | smoke | A2 | 0/2 | 2 |
| [smoke_A3_codestral_all_roles](smoke_A3_codestral_all_roles/) | smoke | A3 | 0/2 | 2 |
| [smoke_A4_devstral_all_roles](smoke_A4_devstral_all_roles/) | smoke | A4 | 0/2 | 2 |
| [smoke_B1_gpt54_codestral_critic](smoke_B1_gpt54_codestral_critic/) | smoke | B1 | 0/2 | 2 |
| [pilot_A1_gpt54_all_roles](pilot_A1_gpt54_all_roles/) | all_task_pilot | A1 | 60/60 | 0 |
| [pilot_A2_gpt54mini_all_roles](pilot_A2_gpt54mini_all_roles/) | all_task_pilot | A2 | 60/60 | 0 |
| [pilot_A3_codestral_all_roles](pilot_A3_codestral_all_roles/) | all_task_pilot | A3 | 60/60 | 0 |
| [pilot_A4_devstral_all_roles](pilot_A4_devstral_all_roles/) | all_task_pilot | A4 | 60/60 | 0 |
| [pilot_B1_gpt54_codestral_critic](pilot_B1_gpt54_codestral_critic/) | all_task_pilot | B1 | 60/60 | 0 |
| [confirm_A1_gpt54_all_roles](confirm_A1_gpt54_all_roles/) | paired_confirmation | A1 | 154/200 | 46 |
| [confirm_B1_gpt54_codestral_critic](confirm_B1_gpt54_codestral_critic/) | paired_confirmation | B1 | 154/200 | 46 |

Current canonical evidence contains **608/710** planned
trace files. The missing set consists of 10 Smoke traces and 92 Confirmation
traces (46 for A1 and 46 for B1).

The prior long Run/Restart layout is preserved in Git commit
`1dd06c485df34a10db990f051972d7b190e7946e`. It contains 703 raw trace files, including 92 quota-error
artifacts, two restart duplicates, and one partial trace. Those artifacts are
not presented as canonical trials here.

## Existing historical configurations

- [version_1_trial_traces](version_1_trial_traces/)
- [version_2_trial_traces](version_2_trial_traces/)
- [version_3_trial_traces](version_3_trial_traces/)

Historical Qwen evidence is preserved. This model-matrix experiment makes no new
Qwen calls.
