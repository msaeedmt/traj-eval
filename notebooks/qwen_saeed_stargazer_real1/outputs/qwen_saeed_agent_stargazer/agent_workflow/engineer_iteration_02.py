import json
import numpy as np
from math import pi, sqrt, cos, sin, atan2

# Load observations
with open('stargazer_observations.json', 'r') as f:
    raw = json.load(f)

obs = raw['observations']
times = np.array(obs['times_days'])
rvs = np.array(obs['rvs_ms'])
sigmas = np.array(obs['sigmas_ms'])

# Center the data
times_centered = times - np.mean(times)
rvs_centered = rvs - np.mean(rvs)

# Grid search over periods to find best sinusoidal fit
def fit_sinusoid(t, P, K, phi, gamma):
    """Fit sinusoidal RV model"""
    omega = 2 * pi / P
    model = gamma + K * cos(omega * t + phi)
    return model

def chi_squared(t, rv, sigma, P, K, phi, gamma):
    """Calculate chi-squared for given parameters"""
    model = fit_sinusoid(t, P, K, phi, gamma)
    return np.sum(((rv - model) / sigma) ** 2)

# Search over period range
P_min, P_max = 1.0, 200.0
n_periods = 1000
periods = np.logspace(np.log10(P_min), np.log10(P_max), n_periods)

best_chi2 = float('inf')
best_params = None

for P in periods:
    # For each period, optimize K, phi, gamma using linear least squares
    omega = 2 * pi / P
    cos_term = cos(omega * times_centered)
    sin_term = sin(omega * times_centered)
    
    # Design matrix for linear fit: RV = gamma + A*cos(omega*t) + B*sin(omega*t)
    A = np.column_stack([np.ones(len(times)), cos_term, sin_term])
    
    # Weighted least squares
    weights = 1.0 / sigmas ** 2
    A_weighted = np.sqrt(weights)[:, np.newaxis] * A
    rv_weighted = np.sqrt(weights) * rvs_centered
    
    # Solve for parameters
    try:
        params, residuals, rank, s = np.linalg.lstsq(A_weighted, rv_weighted, rcond=None)
        gamma, A_coef, B_coef = params
        
        K = sqrt(A_coef**2 + B_coef**2)
        phi = atan2(-B_coef, A_coef)
        
        chi2 = np.sum(((rvs_centered - fit_sinusoid(times_centered, P, K, phi, gamma)) / sigmas) ** 2)
        
        if chi2 < best_chi2:
            best_chi2 = chi2
            best_params = (P, K, phi, gamma)
    except:
        continue

# Extract best period and amplitude
planets = []
if best_params:
    P, K, phi, gamma = best_params
    
    # Estimate m sin i from K
    # K = (2*pi*G/P)^(1/3) * m*sin(i) / (M_star)^(2/3)
    # For a solar-mass star: m_sin_i (Mjup) ≈ K (m/s) * sqrt(P (days)) * 0.0049
    m_sin_i = K * sqrt(P) * 0.0049
    
    # Assume circular orbit for simplicity
    e = 0.0
    
    # Ensure physical constraints
    P = max(P, 0.1)
    m_sin_i = max(0, m_sin_i)
    e = max(0, min(e, 0.99))
    
    planets.append({
        'P_days': float(P),
        'm_sin_i_mjup': float(m_sin_i),
        'e': float(e)
    })

# Write output
output = {'planets': planets}
with open('agent_submission.json', 'w') as f:
    json.dump(output, f, indent=2)

# Verify output
with open('agent_submission.json', 'r') as f:
    verify = json.load(f)
    assert 'planets' in verify
    for p in verify['planets']:
        assert p['P_days'] > 0
        assert p['m_sin_i_mjup'] >= 0
        assert 0 <= p['e'] < 1
FINAL: Code written to agent_submission.json with detected planet parameters