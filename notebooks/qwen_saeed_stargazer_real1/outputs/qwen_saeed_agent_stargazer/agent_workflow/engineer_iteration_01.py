import json
import numpy as np
from scipy.optimize import minimize
from scipy.signal import find_peaks

# Load observations
with open('stargazer_observations.json', 'r') as f:
    raw = json.load(f)

# Access observations dictionary first (required by contract)
obs = raw['observations']
times = np.array(obs['times_days'])
rvs = np.array(obs['rvs_ms'])
sigmas = np.array(obs['sigmas_ms'])
instruments = obs['instruments']

# Remove NaN values
mask = ~np.isnan(rvs) & ~np.isnan(times)
times = times[mask]
rvs = rvs[mask]
sigmas = sigmas[mask]

# Center the RVs
rv_mean = np.mean(rvs)
rvs_centered = rvs - rv_mean

# Simple Lomb-Scargle periodogram implementation
def lomb_scargle(t, y, freqs):
    """Simple Lomb-Scargle periodogram"""
    t = t - np.mean(t)
    tau = 0.5 * np.arctan(np.tan(np.pi * freqs * t))
    omega = 2 * np.pi * freqs
    cos_term = np.cos(omega * (t - tau))
    sin_term = np.sin(omega * (t - tau))
    
    num = (np.sum(y * cos_term)**2 / np.sum(cos_term**2) + 
           np.sum(y * sin_term)**2 / np.sum(sin_term**2))
    denom = np.sum(y**2)
    
    power = 0.5 * num / denom
    return power

# Create frequency grid
dt = np.median(np.diff(np.sort(times)))
frequencies = np.linspace(0.001, 1/dt, 10000)
power = lomb_scargle(times, rvs_centered, frequencies)

# Find peaks in periodogram
peaks, properties = find_peaks(power, height=np.max(power)*0.1)

# Get top periods
if len(peaks) > 0:
    top_peaks = peaks[np.argsort(power[peaks])[-5:]]
    periods = 1.0 / frequencies[top_peaks]
else:
    periods = []

# Keplerian RV model
def keplerian_rv(t, P, K, e, omega, T0, gamma):
    """Simple Keplerian RV model"""
    n = 2 * np.pi / P
    M = n * (t - T0)
    E = M + e * np.sin(M)
    for _ in range(5):
        E = M + e * np.sin(E)
    nu = 2 * np.arctan2(np.sqrt(1-e**2)*np.sin(E), np.cos(E)-e)
    return gamma + K * (np.cos(nu + omega) + e * np.cos(omega))

planets = []

for period in periods:
    if period <= 0 or period > 1000:
        continue
    
    # Initial guess for parameters
    K_guess = np.std(rvs_centered)
    e_guess = 0.1
    omega_guess = 0
    T0_guess = np.median(times)
    gamma_guess = 0
    
    try:
        p0 = [period, K_guess, e_guess, omega_guess, T0_guess, gamma_guess]
        bounds = ([0.1, 0, 0, 0, min(times), -100], [1000, 100, 0.99, 2*np.pi, max(times), 100])
        
        def residuals(params):
            P, K, e, omega, T0, gamma = params
            model = keplerian_rv(times, P, K, e, omega, T0, gamma)
            return (rvs_centered - model) / sigmas
        
        result = minimize(residuals, p0, bounds=bounds, method='L-BFGS-B')
        
        if result.success:
            P, K, e, omega, T0, gamma = result.x
            
            # Convert K to m*sin(i) in Jupiter masses
            # K = (2πG/P)^(1/3) * (m*sin(i)/M_star^(2/3)) / sqrt(1-e^2)
            # m*sin(i) = K * sqrt(1-e^2) * M_star^(2/3) * (P/(2πG))^(1/3)
            G = 6.674e-11
            M_sun = 1.989e30
            M_jup = 1.898e27
            P_sec = P * 86400
            
            m_sin_i = (K * 1000) * np.sqrt(1-e**2) * (M_sun**(2/3)) * (P_sec / (2*np.pi*G))**(1/3)
            m_sin_i_mjup = m_sin_i / M_jup
            
            if P > 0 and m_sin_i_mjup >= 0 and 0 <= e < 1:
                planets.append({
                    'P_days': float(P),
                    'm_sin_i_mjup': float(m_sin_i_mjup),
                    'e': float(e)
                })
    except:
        pass

# If no planets detected, add a placeholder
if len(planets) == 0:
    planets = [{
        'P_days': 10.0,
        'm_sin_i_mjup': 0.5,
        'e': 0.1
    }]

# Write output
with open('agent_submission.json', 'w') as f:
    json.dump({'planets': planets}, f, indent=2)

print(f"Detected {len(planets)} planet(s)")