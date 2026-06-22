#!/usr/bin/env python3
"""
Stargazer Real Task 001 - Public Data Fit Script

This script:
1. Reads public observations from stargazer_observations.json
2. Detrends per-instrument radial velocities
3. Searches for candidate periods using sinusoidal least squares
4. Fits the best period to derive P_days, m_sin_i_mjup, and sigma_jitter_ms
5. Writes agent_submission.json and fit_diagnostics.json
"""

import json
import os
import numpy as np
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).parent.resolve()
WORKDIR = SCRIPT_DIR / "stargazer_workdir"
OBS_FILE = Path("notebooks/qwen_saeed_stargazer_real1/tasks/stargazer_real_real_001_minimal/stargazer_observations.json")
SUBMISSION_FILE = WORKDIR / "agent_submission.json"
DIAGNOSTICS_FILE = WORKDIR / "fit_diagnostics.json"

# Constants for mass conversion
# m_sin_i (Mjup) = K (m/s) * sqrt(1-e^2) * (P_days/365.25)^(1/3) * M_star^(2/3) / 28.432
# Assuming M_star = 1.0 Msun, e = 0.0
# m_sin_i_mjup = K_ms * (P_days/365.25)^(1/3) / 28.432 * 1000 (K is in m/s, but we have ms)
# Actually K in m/s: K_ms * 1000 = K_mps
# m_sin_i_mjup = K_mps * (P_days/365.25)^(1/3) / 28.432
# = K_ms * 1000 * (P_days/365.25)^(1/3) / 28.432
# = K_ms * 35.17 * (P_days/365.25)^(1/3)

def load_observations():
    """Load public observations."""
    with open(OBS_FILE, 'r') as f:
        data = json.load(f)
    return data["observations"]

def detrend_per_instrument(obs):
    """Detrend radial velocities per instrument by subtracting instrument mean."""
    instruments = obs["instruments"]
    rvs = np.array(obs["rvs_ms"])
    times = np.array(obs["times_days"])
    sigmas = np.array(obs["sigmas_ms"])

    # Get unique instruments
    unique_instruments = np.unique(instruments)

    # Detrend: subtract mean per instrument
    detrended_rvs = rvs.copy()
    for inst in unique_instruments:
        mask = np.array(instruments) == inst
        inst_mean = np.mean(rvs[mask])
        detrended_rvs[mask] -= inst_mean

    return times, detrended_rvs, sigmas, instruments

def sinusoidal_least_squares(times, rvs, period):
    """Fit a sinusoid to the data for a given period.

    Model: rv = K * sin(2*pi*t/P + phi) + offset
    Returns: K (semi-amplitude), phi, offset, residual_rms
    """
    t = times
    y = rvs
    P = period

    # Phase
    phase = 2 * np.pi * t / P

    # Linear least squares for A*sin(phase) + B*cos(phase) + C
    # y = A*sin + B*cos + C
    # K = sqrt(A^2 + B^2), phi = atan2(B, A)

    X = np.column_stack([np.sin(phase), np.cos(phase), np.ones_like(t)])

    # Solve least squares
    try:
        coeffs, residuals, rank, s = np.linalg.lstsq(X, y, rcond=None)
    except:
        return None, None, None, None

    A, B, C = coeffs
    K = np.sqrt(A**2 + B**2)
    phi = np.arctan2(B, A)

    # Predicted values
    y_pred = A * np.sin(phase) + B * np.cos(phase) + C

    # Residual RMS
    residual_rms = np.sqrt(np.mean((y - y_pred)**2))

    return K, phi, C, residual_rms

def search_periods(times, rvs, period_range=(1, 1000), n_periods=1000):
    """Search for the best period using sinusoidal least squares."""
    periods = np.linspace(period_range[0], period_range[1], n_periods)

    best_period = None
    best_K = 0
    best_residual = float('inf')

    results = []

    for P in periods:
        K, phi, offset, residual_rms = sinusoidal_least_squares(times, rvs, P)
        if K is not None:
            results.append({
                'period': P,
                'K_ms': K,
                'residual_rms': residual_rms
            })
            # Prefer lower residual, but also require significant K
            if residual_rms < best_residual and K > 1.0:  # K > 1 m/s threshold
                best_residual = residual_rms
                best_period = P
                best_K = K

    return best_period, best_K, best_residual, results

def fit_best_period(times, rvs, period):
    """Fit the best period and return detailed parameters."""
    K, phi, offset, residual_rms = sinusoidal_least_squares(times, rvs, period)

    # Calculate m_sin_i in Jupiter masses
    # m_sin_i_mjup = K_ms * 35.17 * (P_days/365.25)^(1/3)
    m_sin_i_mjup = K * 35.17 * (period / 365.25)**(1/3)

    # Estimate jitter as residual RMS (could be refined with instrument sigmas)
    sigma_jitter_ms = residual_rms

    return {
        'P_days': period,
        'K_ms': K,
        'm_sin_i_mjup': m_sin_i_mjup,
        'sigma_jitter_ms': sigma_jitter_ms,
        'phi_rad': phi,
        'offset_ms': offset
    }

def main():
    print("Loading observations...")
    obs = load_observations()

    print(f"Loaded {len(obs['times_days'])} observations from {len(np.unique(obs['instruments']))} instruments")

    print("Detrending per instrument...")
    times, detrended_rvs, sigmas, instruments = detrend_per_instrument(obs)

    print("Searching for best period...")
    best_period, best_K, best_residual, all_results = search_periods(
        times, detrended_rvs,
        period_range=(1, 500),  # Search 1-500 days
        n_periods=2000
    )

    if best_period is None:
        print("No significant period found. Using fallback.")
        best_period = 100.0
        best_K = 5.0
        best_residual = 10.0

    print(f"Best period: {best_period:.2f} days, K: {best_K:.2f} m/s, residual: {best_residual:.2f} m/s")

    print("Fitting best period...")
    fit_result = fit_best_period(times, detrended_rvs, best_period)

    print(f"Fit result: P={fit_result['P_days']:.2f} days, m_sin_i={fit_result['m_sin_i_mjup']:.4f} Mjup, jitter={fit_result['sigma_jitter_ms']:.2f} m/s")

    # Create workdir
    WORKDIR.mkdir(parents=True, exist_ok=True)

    # Write submission
    submission = {
        "planets": [
            {
                "P_days": fit_result['P_days'],
                "m_sin_i_mjup": fit_result['m_sin_i_mjup'],
                "e": 0.0,
                "inc_rad": 1.5707963267948966,
                "Omega_rad": 0.0,
                "omega_rad": 0.0,
                "l_rad": 0.0
            }
        ],
        "noise": {
            "sigma_jitter_ms": fit_result['sigma_jitter_ms']
        },
        "metadata": {
            "source": "qwen_public_fit",
            "task_id": "real_001",
            "fit_method": "sinusoidal_least_squares_period_search"
        }
    }

    with open(SUBMISSION_FILE, 'w') as f:
        json.dump(submission, f, indent=2)

    print(f"Submission written to {SUBMISSION_FILE}")

    # Write diagnostics
    diagnostics = {
        "tested_period_count": len(all_results),
        "best_period_days": fit_result['P_days'],
        "best_K_ms": fit_result['K_ms'],
        "m_sin_i_mjup": fit_result['m_sin_i_mjup'],
        "residual_rms_ms": fit_result['sigma_jitter_ms'],
        "sigma_jitter_ms": fit_result['sigma_jitter_ms'],
        "submission_path": str(SUBMISSION_FILE),
        "observation_count": len(times),
        "instrument_count": len(np.unique(instruments)),
        "time_range_days": [float(times.min()), float(times.max())]
    }

    with open(DIAGNOSTICS_FILE, 'w') as f:
        json.dump(diagnostics, f, indent=2)

    print(f"Diagnostics written to {DIAGNOSTICS_FILE}")
    print("Done!")

if __name__ == "__main__":
    main()
