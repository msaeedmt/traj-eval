import json
import numpy as np

def load_observations(filepath):
    """Load observations from JSON file"""
    with open(filepath, 'r') as f:
        raw = json.load(f)
    obs = raw['observations']
    return obs

def compute_lomb_scargle_periodogram(times, rvs, sigmas):
    """Compute Lomb-Scargle periodogram using numpy only"""
    t = np.array(times, dtype=np.float64)
    y = np.array(rvs, dtype=np.float64)
    w = 1.0 / np.array(sigmas, dtype=np.float64)
    
    # Normalize time
    t_mean = np.mean(t)
    t_centered = t - t_mean
    
    # Frequency range: from 1/(2*span) to 1/(span/100)
    t_span = np.max(t) - np.min(t)
    n_freqs = 2000
    freqs = np.linspace(1.0/(t_span*2), 1.0/(t_span/100), n_freqs)
    
    powers = np.zeros(n_freqs)
    
    for i, freq in enumerate(freqs):
        omega = 2 * np.pi * freq
        tau = np.arctan2(np.sum(w * np.sin(omega * t_centered)), 
                        np.sum(w * np.cos(omega * t_centered)))
        
        cos_term = np.cos(omega * (t_centered - tau))
        sin_term = np.sin(omega * (t_centered - tau))
        
        # Lomb-Scargle power
        num_cos = np.sum(w * y * cos_term)
        num_sin = np.sum(w * y * sin_term)
        den_cos = np.sum(w * cos_term**2)
        den_sin = np.sum(w * sin_term**2)
        
        if den_cos > 0 and den_sin > 0:
            powers[i] = 0.5 * (num_cos**2 / den_cos + num_sin**2 / den_sin)
    
    return freqs, powers

def find_peaks(powers, freqs, min_separation=3, threshold_factor=3.0):
    """Find peaks in periodogram using numpy only"""
    n = len(powers)
    peaks = []
    
    # Calculate threshold (mean + threshold_factor * std)
    threshold = np.mean(powers) + threshold_factor * np.std(powers)
    
    for i in range(min_separation, n - min_separation):
        # Check if this is a local maximum
        is_max = True
        for j in range(1, min_separation + 1):
            if powers[i] <= powers[i - j] or powers[i] <= powers[i + j]:
                is_max = False
                break
        
        if is_max and powers[i] > threshold:
            peaks.append((freqs[i], powers[i]))
    
    # Sort by power (descending)
    peaks.sort(key=lambda x: x[1], reverse=True)
    return peaks

def compute_keplerian_rv(t, P, K, e, omega, M0):
    """Compute radial velocity for Keplerian orbit"""
    t = np.array(t)
    n = 2 * np.pi / P
    M = n * t + M0
    
    # Solve Kepler's equation iteratively
    E = M.copy()
    for _ in range(10):
        E = M + e * np.sin(E)
    
    # True anomaly
    nu = 2 * np.arctan2(np.sqrt(1 + e) * np.sin(E/2), 
                       np.sqrt(1 - e) * np.cos(E/2))
    
    # Radial velocity
    rv = K * (np.cos(nu + omega) + e * np.cos(omega))
    return rv

def fit_keplerian_params(times, rvs, sigmas, period):
    """Fit Keplerian parameters for a given period using grid search"""
    t = np.array(times, dtype=np.float64)
    y = np.array(rvs, dtype=np.float64)
    w = 1.0 / np.array(sigmas, dtype=np.float64)
    
    # Grid search over K, e, omega, M0
    best_chi2 = np.inf
    best_params = None
    
    # Reasonable ranges
    K_range = np.linspace(0.1, 50.0, 20)  # m/s
    e_range = np.linspace(0.0, 0.5, 10)   # eccentricity
    omega_range = np.linspace(0, 2*np.pi, 12)
    M0_range = np.linspace(0, 2*np.pi, 12)
    
    for K in K_range:
        for e in e_range:
            for omega in omega_range:
                for M0 in M0_range:
                    rv_model = compute_keplerian_rv(t, period, K, e, omega, M0)
                    residuals = y - rv_model
                    chi2 = np.sum(w * residuals**2)
                    
                    if chi2 < best_chi2:
                        best_chi2 = chi2
                        best_params = (K, e, omega, M0)
    
    if best_params is None:
        return None
    
    return best_params

def compute_m_sin_i(K, P, e, M_star_msun=1.0):
    """Compute m*sin(i) in Jupiter masses from K, P, e"""
    # Constants
    G = 6.67430e-11  # m^3 kg^-1 s^-1
    M_sun = 1.989e30  # kg
    M_jup = 1.898e27  # kg
    day_to_sec = 86400
    
    # Convert to SI units
    K_si = K  # m/s
    P_si = P * day_to_sec  # seconds
    M_star_si = M_star_msun * M_sun
    
    # m*sin(i) = K * sqrt(1-e^2) * (P/(2*pi*G))^(1/3) * M_star^(2/3)
    m_sin_i_si = K_si * np.sqrt(1 - e**2) * (P_si / (2 * np.pi * G))**(1/3) * M_star_si**(2/3)
    
    # Convert to Jupiter masses
    m_sin_i_mjup = m_sin_i_si / M_jup
    
    return m_sin_i_mjup

def analyze_radial_velocity(obs):
    """Main analysis function"""
    times = np.array(obs['times_days'], dtype=np.float64)
    rvs = np.array(obs['rvs_ms'], dtype=np.float64)
    sigmas = np.array(obs['sigmas_ms'], dtype=np.float64)
    
    # Compute periodogram
    freqs, powers = compute_lomb_scargle_periodogram(times, rvs, sigmas)
    
    # Find peaks
    peaks = find_peaks(powers, freqs)
    
    planets = []
    
    for freq, power in peaks:
        period = 1.0 / freq  # Convert frequency to period
        
        # Fit Keplerian parameters
        params = fit_keplerian_params(times, rvs, sigmas, period)
        
        if params is None:
            continue
        
        K, e, omega, M0 = params
        
        # Validate parameters
        if period <= 0:
            continue
        if e < 0 or e >= 1:
            continue
        if K <= 0:
            continue
        
        # Compute m*sin(i)
        m_sin_i = compute_m_sin_i(K, period, e)
        
        if m_sin_i < 0:
            continue
        
        planets.append({
            'P_days': float(period),
            'm_sin_i_mjup': float(m_sin_i),
            'e': float(e)
        })
    
    # Remove duplicate periods (within 10%)
    unique_planets = []
    for p in planets:
        is_duplicate = False
        for up in unique_planets:
            if abs(p['P_days'] - up['P_days']) / max(p['P_days'], up['P_days']) < 0.1:
                is_duplicate = True
                break
        if not is_duplicate:
            unique_planets.append(p)
    
    return unique_planets

def main():
    # Load observations
    obs = load_observations('stargazer_observations.json')
    
    # Analyze radial velocity data
    planets = analyze_radial_velocity(obs)
    
    # Write output
    output = {'planets': planets}
    with open('agent_submission.json', 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"Analysis complete. Found {len(planets)} planet(s).")
    print(f"Output written to agent_submission.json")

if __name__ == '__main__':
    main()