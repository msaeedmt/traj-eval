# Astro dataset provenance

Task files converted from AIPS-UofT/Stargazer by
`scripts/prepare_astro_dataset.py`.

- upstream checkout: `/tmp/Stargazer`
- upstream commit: `3f617667472061e253288c7b26f0e70f186f2dff`
- conversion applied: `bank._apply_rv_only_compat`
  (REBOUND signal replaced by analytic multi-Keplerian, noise realisation
  preserved; `l_rad -= Omega_rad`, `Omega_rad = 0`)
- task data licence: CC-BY-4.0 (code is MIT; see
  `src/traj_eval/vendor/stargazer/LICENSE`)

This is exactly the conversion upstream performs at load time in both
`TaskBank.load_task` and `RvEnv.reset`, so scoring stays comparable to the
published baseline. Baking it in removes `rebound` and `celerite2` from the
runtime dependency set.

## Counts

- **synthetic**: ok_rv_only_compat=100
- **real**: ok_rv_only=20
