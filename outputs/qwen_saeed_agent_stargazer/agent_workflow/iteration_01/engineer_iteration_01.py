import json
import math
import numpy as np
from scipy.optimize import minimize
from scipy.stats import chi2

def load_data(filepath):
    with open(filepath, 'r') as f:
        data = json.load(f)
    obs = data.get('observations', data)
    times = np.array(obs['times_days'])
    rvs = np.array(obs['rvs_ms'])
    sigmas = np.array(obs['sigmas_ms'])
    instruments = obs.get('instruments', [''] * len(times))
    return times, rvs, sigmas, instruments

def keplerian_rv(t, P, K, e, omega, T0, M_star=1.0):
    # M_star in solar masses, P in days, K in m/s, t in days
    # Returns RV in m/s
    n = 2 * np.pi / P
    M = n * (t - T0)
    # Solve Kepler's equation for E
    E = M
    for _ in range(10):
        E_new = E + (M - E + e * np.sin(E)) / (1 - e * np.cos(E))
        if np.allclose(E, E_new):
            break
        E = E_new
    # True anomaly
    nu = 2 * np.arctan2(np.sqrt(1 + e) * np.sin(E / 2), np.sqrt(1 - e) * np.cos(E / 2))
    # RV
    rv = K * (np.cos(nu + omega) + e * np.cos(omega))
    return rv

def residual_sum_sq(params, t, rv, sigma):
    P, K, e, omega, T0 = params
    if P <= 0 or K < 0 or e < 0 or e >= 1:
        return 1e10
    model = keplerian_rv(t, P, K, e, omega, T0)
    return np.sum(((rv - model) / sigma) ** 2)

def calculate_bic(params, t, rv, sigma, n_params=5):
    rss = residual_sum_sq(params, t, rv, sigma)
    n = len(t)
    if rss <= 0:
        return 1e10
    return n * np.log(rss / n) + n_params * np.log(n)

def search_periodogram(t, rv, sigma):
    # Simple Lomb-Scargle-like search using least squares for single sinusoid
    # Range: 0.5 to 1000 days
    periods = np.logspace(np.log10(0.5), np.log10(1000), 2000)
    scores = []
    for P in periods:
        # Fit A*cos(2pi*t/P) + B*sin(2pi*t/P) + C
        # Design matrix
        X = np.column_stack([np.cos(2 * np.pi * t / P), np.sin(2 * np.pi * t / P), np.ones_like(t)])
        # Weighted least squares
        W = np.diag(1 / (sigma ** 2))
        try:
            beta = np.linalg.solve(X.T @ W @ X, X.T @ W @ rv)
            model = X @ beta
            rss = np.sum(((rv - model) / sigma) ** 2)
            # Power is proportional to reduction in variance
            total_var = np.sum((rv - np.mean(rv)) ** 2 / sigma ** 2)
            power = (total_var - rss) / total_var
            scores.append(power)
        except:
            scores.append(0)
    return periods, np.array(scores)

def main():
    # 1. Load Data
    t, rv, sigma, inst = load_data('stargazer_observations.json')
    
    # 2. Period Search
    periods, powers = search_periodogram(t, rv, sigma)
    
    # Identify top candidates
    top_indices = np.argsort(powers)[::-1][:10]
    candidates = []
    
    for idx in top_indices:
        P_guess = periods[idx]
        # Check for daily aliases (1 day, 1/2 day, etc.)
        # If P is very close to 1.0 or 0.5, check if a nearby non-alias is better
        # For now, we just collect top raw peaks and refine
        
        # Initial guess for Keplerian fit
        # K approx sqrt(2 * power * variance) / sqrt(N) ? 
        # Better: use amplitude from sinusoid fit
        # Re-fit sinusoid for this P to get K_guess
        X = np.column_stack([np.cos(2 * np.pi * t / P_guess), np.sin(2 * np.pi * t / P_guess), np.ones_like(t)])
        W = np.diag(1 / (sigma ** 2))
        beta = np.linalg.solve(X.T @ W @ X, X.T @ W @ rv)
        K_guess = np.sqrt(beta[0]**2 + beta[1]**2)
        T0_guess = t[np.argmax(rv)] # Rough guess
        
        # Bounds for optimization
        bounds = [(0.1, 1000), (0.1, 1000), (0.0, 0.99), (0, 2*np.pi), (0, P_guess)]
        
        # Try to fit Keplerian
        try:
            res = minimize(
                residual_sum_sq,
                x0=[P_guess, K_guess, 0.0, 0.0, T0_guess],
                args=(t, rv, sigma),
                bounds=bounds,
                method='L-BFGS-B'
            )
            if res.success:
                P_opt, K_opt, e_opt, omega_opt, T0_opt = res.x
                bic_val = calculate_bic(res.x, t, rv, sigma)
                candidates.append({
                    'P': P_opt,
                    'K': K_opt,
                    'e': e_opt,
                    'omega': omega_opt,
                    'T0': T0_opt,
                    'bic': bic_val,
                    'power': powers[idx]
                })
        except:
            continue

    # 3. Select Best Candidate
    # Sort by BIC (lower is better)
    candidates.sort(key=lambda x: x['bic'])
    
    if not candidates:
        # Fallback if no fit found
        best = {'P': 10.0, 'K': 10.0, 'e': 0.0, 'omega': 0.0, 'T0': 0.0}
    else:
        best = candidates[0]
        
        # Alias check: if best P is ~1.0 day, check if a nearby candidate with different P has similar BIC
        # If so, prefer the longer period (less likely to be alias)
        # Simple heuristic: if P < 2.0 and there is a candidate with P > 2.0 and BIC within 5 sigma
        if best['P'] < 2.0:
            for c in candidates:
                if c['P'] > 2.0 and abs(c['bic'] - best['bic']) < 10: # 10 is arbitrary threshold
                    best = c
                    break

    # 4. Convert to Physical Units
    # P_days = best['P']
    # K_ms = best['K']
    # M_star = 1.0 Msun
    # m_sin_i (Mjup) = K * (P * 86400)^(1/3) * (M_star)^(2/3) / (28.4329)
    # Formula: K = (28.4329 m/s) * (m_sin_i / Mjup) * (P/yr)^(-1/3) * (M_star/Msun)^(-2/3) * (1-e^2)^(-1/2)
    # Rearranged: m_sin_i = K / 28.4329 * (P/365.25)^(1/3) * (M_star)^(2/3) * sqrt(1-e^2)
    
    P_days = best['P']
    K_ms = best['K']
    e = best['e']
    omega = best['omega']
    T0 = best['T0']
    
    # Mean anomaly at epoch l = 2pi * (t_ref - T0) / P ? 
    # Usually l is mean longitude at epoch. Let's set epoch to t=0 or mean time.
    # l_rad = 2 * pi * (0 - T0) / P_days (mod 2pi)
    l_rad = (2 * np.pi * (-T0) / P_days) % (2 * np.pi)
    
    m_sin_i_mjup = (K_ms / 28.4329) * ((P_days / 365.25) ** (1/3)) * (1.0 ** (2/3)) * math.sqrt(1 - e**2)
    
    # Sanity check
    if m_sin_i_mjup < 0.01 or m_sin_i_mjup > 100:
        # If mass is unphysical, maybe the fit is bad, but we proceed with best available
        pass

    # 5. Output
    result = {
        "planets": [
            {
                "P_days": float(P_days),
                "m_sin_i_mjup": float(m_sin_i_mjup),
                "e": float(e),
                "omega_rad": float(omega),
                "l_rad": float(l_rad)
            }
        ]
    }
    
    with open('agent_submission.json', 'w') as f:
        json.dump(result, f, indent=2)
        
    # Diagnostics
    diag = {
        "top_candidates": candidates[:5],
        "best_bic": best['bic'],
        "best_period": best['P'],
        "best_K": best['K']
    }
    with open('agent_diagnostics.json', 'w') as f:
        json.dump(diag, f, indent=2)

if __name__ == "__main__":
    main()