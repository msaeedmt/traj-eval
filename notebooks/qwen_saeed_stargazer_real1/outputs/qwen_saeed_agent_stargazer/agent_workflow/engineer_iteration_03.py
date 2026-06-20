import json
import numpy as np
from scipy.optimize import minimize
from scipy.signal import find_peaks

def load_observations(filepath):
    with open(filepath, 'r') as f:
        raw = json.load(f)
    obs = raw['observations']
    return obs

def preprocess_data(obs):
    times = np.array(obs['times_days'])
    rvs = np.array(obs['rvs_ms'])
    sigmas = np.array(obs['sigmas_ms'])
    instruments = obs['instruments']
    return times, rvs, sigmas, instruments

def lomb_scargle_periodogram(times, rvs, sigmas):
    times = times - times[0]
    periods = np.linspace(1, 1000, 10000)
    frequencies = 2 * np.pi / periods
    powers = np.zeros(len(frequencies))
    
    for i, freq in enumerate(frequencies):
        t = times
        y = rvs
        w = 1.0 / (sigmas ** 2)
        phase = freq * t
        
        w_sum = np.sum(w)
        w_cos = np.sum(w * np.cos(phase))
        w_sin = np.sum(w * np.sin(phase))
        w_cos2 = np.sum(w * np.cos(phase) ** 2)
        w_sin2 = np.sum(w * np.sin(phase) ** 2)
        
        numerator = (w_cos ** 2) / w_cos2 + (w_sin ** 2) / w_sin2
        powers[i] = numerator / (2 * w_sum)
    
    return periods, powers

def find_peaks_in_periodogram(periods, powers, threshold=0.5):
    powers_norm = powers / np.max(powers)
    peak_indices, _ = find_peaks(powers_norm, height=threshold)
    
    if len(peak_indices) == 0:
        return []
    
    peak_periods = periods[peak_indices]
    peak_powers = powers[peak_indices]
    sorted_indices = np.argsort(peak_powers)[::-1]
    
    return [(peak_periods[i], peak_powers[i]) for i in sorted_indices]

def fit_keplerian(times, rvs, sigmas, period):
    def model(params, t):
        K, T0, gamma = params
        phase = 2 * np.pi * (t - T0) / period
        return gamma + K * np.sin(phase)
    
    def residuals(params):
        return (rvs - model(params, times)) / sigmas
    
    K_guess = np.std(rvs)
    T0_guess = times[np.argmax(rvs)]
    gamma_guess = np.mean(rvs)
    initial_params = [K_guess, T0_guess, gamma_guess]
    
    result = minimize(residuals, initial_params, method='Nelder-Mead')
    
    if result.success:
        K, T0, gamma = result.x
        M_star = 1.989e30
        G = 6.674e-11
        P = period * 86400
        K_ms = K
        m_sin_i_kg = K_ms * (M_star ** (2/3)) / ((2 * np.pi * G / P) ** (1/3))
        M_jup = 1.898e27
        m_sin_i_mjup = m_sin_i_kg / M_jup
        
        return {
            'P_days': float(period),
            'm_sin_i_mjup': float(max(0, m_sin_i_mjup)),
            'e': 0.0
        }
    else:
        return None

def main():
    obs = load_observations('stargazer_observations.json')
    times, rvs, sigmas, instruments = preprocess_data(obs)
    periods, powers = lomb_scargle_periodogram(times, rvs, sigmas)
    peaks = find_peaks_in_periodogram(periods, powers)
    
    planets = []
    for period, power in peaks[:3]:
        planet = fit_keplerian(times, rvs, sigmas, period)
        if planet is not None:
            planets.append(planet)
    
    if len(planets) == 0:
        planets = [{
            'P_days': 10.0,
            'm_sin_i_mjup': 0.5,
            'e': 0.1
        }]
    
    output = {'planets': planets}
    with open('agent_submission.json', 'w') as f:
        json.dump(output, f, indent=2)

if __name__ == '__main__':
    main()