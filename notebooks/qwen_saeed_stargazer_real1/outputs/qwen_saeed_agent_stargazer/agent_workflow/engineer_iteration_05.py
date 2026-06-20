import json
import numpy as np
from scipy.optimize import minimize
from scipy.signal import find_peaks
import warnings
warnings.filterwarnings('ignore')

def load_observations(filepath='stargazer_observations.json'):
    """Load observations from JSON file."""
    with open(filepath, 'r') as f:
        raw = json.load(f)
    obs = raw['observations']
    return obs

def preprocess_data(obs):
    """Preprocess observation data."""
    times = np.array(obs['times_days'])
    rvs = np.array(obs['rvs_ms'])
    sigmas = np.array(obs['sigmas_ms'])
    instruments = np.array(obs['instruments'])
    return times, rvs, sigmas, instruments

def lomb_scargle_periodogram(times, rvs, sigmas):
    """Compute Lomb-Scargle periodogram."""
    t = times - times[0]
    t_max = times[-1] - times[0]
    
    # Frequency range: 2 cycles to Nyquist frequency
    f_min = 2.0 / t_max
    f_max = 0.5 / (times[1] - times[0]) if len(times) > 1 else 1.0
    
    frequencies = np.logspace(np.log10(f_min), np.log10(f_max), 2000)
    powers = np.zeros(len(frequencies))
    
    for i, f in enumerate(frequencies):
        omega = 2 * np.pi * f
        tau = np.arctan(np.sum(sigmas**2 * np.sin(omega * t)) / np.sum(sigmas**2 * np.cos(omega * t)))
        
        cos_omega_t = np.cos(omega * (t - tau))
        sin_omega_t = np.sin(omega * (t - tau))
        
        sigma2 = np.sum(sigmas**2)
        sigma2_cos = np.sum(sigmas**2 * cos_omega_t**2)
        sigma2_sin = np.sum(sigmas**2 * sin_omega_t**2)
        
        numerator = (np.sum(sigmas**2 * rvs * cos_omega_t)**2 / sigma2_cos + 
                    np.sum(sigmas**2 * rvs * sin_omega_t)**2 / sigma2_sin)
        
        powers[i] = numerator / sigma2
    
    return frequencies, powers

def find_period(frequencies, powers):
    """Find the most significant period from periodogram."""
    if len(powers) == 0:
        return None
    
    # Find peaks above threshold
    threshold = np.mean(powers) + 3 * np.std(powers)
    peaks, properties = find_peaks(powers, height=threshold)
    
    if len(peaks) == 0:
        # Fall back to highest power
        best_idx = np.argmax(powers)
        period = 1.0 / frequencies[best_idx]
        return period
    
    # Get the highest peak
    best_peak = peaks[np.argmax(powers[peaks])]
    period = 1.0 / frequencies[best_peak]
    return period

def keplerian_rv_model(t, P, K, e, omega, T0, gamma):
    """Keplerian radial velocity model."""
    M = 2 * np.pi * (t - T0) / P
    
    # Solve Kepler's equation for eccentric anomaly E
    E = M.copy()
    for _ in range(20):
        E_new = M + e * np.sin(E)
        if np.all(np.abs(E_new - E) < 1e-10):
            break
        E = E_new
    
    # True anomaly
    nu = 2 * np.arctan2(np.sqrt(1 + e) * np.sin(E / 2), 
                        np.sqrt(1 - e) * np.cos(E / 2))
    
    # Radial velocity
    rv = K * (np.cos(nu + omega) + e * np.cos(omega)) + gamma
    return rv

def fit_keplerian(times, rvs, sigmas, P_init):
    """Fit Keplerian parameters to RV data."""
    K_init = np.std(rvs) * 2
    e_init = 0.1
    omega_init = 0.0
    T0_init = times[0]
    gamma_init = np.mean(rvs)
    
    def residuals(params):
        P, K, e, omega, T0, gamma = params
        P = max(P, 0.1)
        K = max(K, 0.01)
        e = max(0, min(e, 0.99))
        model = keplerian_rv_model(times, P, K, e, omega, T0, gamma)
        return (rvs - model) / sigmas
    
    result = minimize(residuals, [P_init, K_init, e_init, omega_init, T0_init, gamma_init],
                     method='Nelder-Mead', options={'maxiter': 2000})
    
    if result.success:
        P, K, e, omega, T0, gamma = result.x
        return P, K, e, omega, T0, gamma
    else:
        return None

def compute_minimum_mass(K, P, e, M_star=1.0):
    """Compute minimum mass (m*sin(i)) in Jupiter masses."""
    G = 6.674e-11
    M_sun = 1.989e30
    M_jup = 1.898e27
    day = 86400
    
    K_si = K * 1000
    P_si = P * day
    M_star_si = M_star * M_sun
    
    m_sin_i = (K_si * np.sqrt(1 - e**2) * (P_si * M_star_si**2 / (4 * np.pi**2 * G))**(1/3)) / M_jup
    
    return m_sin_i

def analyze_rv_data(obs):
    """Main RV analysis pipeline."""
    times, rvs, sigmas, instruments = preprocess_data(obs)
    
    # Compute periodogram
    frequencies, powers = lomb_scargle_periodogram(times, rvs, sigmas)
    
    # Find significant periods
    planets = []
    period = find_period(frequencies, powers)
    
    if period is not None:
        # Fit Keplerian model
        fit_result = fit_keplerian(times, rvs, sigmas, period)
        
        if fit_result is not None:
            P, K, e, omega, T0, gamma = fit_result
            
            # Compute minimum mass
            m_sin_i = compute_minimum_mass(K, P, e)
            
            # Validate parameters
            if P > 0 and m_sin_i >= 0 and 0 <= e < 1:
                planets.append({
                    'P_days': float(P),
                    'm_sin_i_mjup': float(m_sin_i),
                    'e': float(e)
                })
    
    return planets

def main():
    # Load observations
    obs = load_observations('stargazer_observations.json')
    
    # Analyze RV data
    planets = analyze_rv_data(obs)
    
    # Write results
    with open('agent_submission.json', 'w') as f:
        json.dump({'planets': planets}, f, indent=2)
    
    print(f"Analysis complete. Found {len(planets)} planet(s).")
    print(f"Results written to agent_submission.json")

if __name__ == '__main__':
    main()