import json
import math
import numpy as np
from scipy.optimize import minimize
from scipy.stats import chi2

def load_data(filename):
    with open(filename, 'r') as f:
        data = json.load(f)
    obs = data.get('observations', data)
    times = np.array(obs['times_days'])
    rvs = np.array(obs['rvs_ms'])
    sigmas = np.array(obs['sigmas_ms'])
    instruments = obs['instruments']
    return times, rvs, sigmas, instruments

def keplerian_rv(t, P, K, e, omega, T0):
    # t in days, P in days, K in m/s
    # Mean anomaly
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

def residual_sum_sq_fixed_P(params, t, rv, sigma, P_fixed):
    # params: [K, e, omega, T0]
    K, e, omega, T0 = params
    if K < 0 or e < 0 or e >= 1:
        return 1e10
    model = keplerian_rv(t, P_fixed, K, e, omega, T0)
    return np.sum(((rv - model) / sigma) ** 2)

def residual_sum_sq_full(params, t, rv, sigma):
    # params: [P, K, e, omega, T0]
    P, K, e, omega, T0 = params
    if P <= 0 or K < 0 or e < 0 or e >= 1:
        return 1e10
    model = keplerian_rv(t, P, K, e, omega, T0)
    return np.sum(((rv - model) / sigma) ** 2)

def calculate_bic(params, t, rv, sigma, n_params=5):
    rss = residual_sum_sq_full(params, t, rv, sigma)
    n = len(t)
    if rss <= 0:
        return 1e10
    return n * np.log(rss / n) + n_params * np.log(n)

def periodogram_search(t, rv, sigma, min_p=1.0, max_p=100.0, n_points=500):
    periods = np.linspace(min_p, max_p, n_points)
    scores = []
    best_params_overall = None
    best_score_overall = 1e10
    
    for P in periods:
        # Initial guess for other parameters
        K_guess = np.std(rv)
        e_guess = 0.1
        omega_guess = 0.0
        T0_guess = t[0]
        
        best_score_local = 1e10
        best_params_local = None
        
        # Try a few random starts or grid for T0
        for T0_init in [t[0], t[len(t)//2], t[-1]]:
            try:
                # Optimize only [K, e, omega, T0] while keeping P fixed
                res = minimize(
                    residual_sum_sq_fixed_P,
                    [K_guess, e_guess, omega_guess, T0_init],
                    args=(t, rv, sigma, P),
                    method='Nelder-Mead',
                    options={'maxiter': 1000}
                )
                if res.fun < best_score_local:
                    best_score_local = res.fun
                    best_params_local = res.x
            except:
                continue
        
        scores.append(best_score_local)
        
        # Track global best to return a good starting point for final refinement
        if best_score_local < best_score_overall:
            best_score_overall = best_score_local
            best_params_overall = [P] + list(best_params_local)
            
    return periods, scores, best_params_overall

def main():
    # Step 1: Load Data
    t, rv, sigma, inst = load_data('stargazer_observations.json')
    
    # Step 2: Numerical Search (Periodogram + Refinement)
    # Search range 1 to 100 days
    periods, scores, best_params_init = periodogram_search(t, rv, sigma, min_p=1.0, max_p=100.0, n_points=200)
    
    # Step 3: Candidate Selection & Alias Check
    # Find top candidates based on RSS (lower is better)
    sorted_indices = np.argsort(scores)
    top_candidates = []
    
    # Check top 5 candidates
    for idx in sorted_indices[:5]:
        P = periods[idx]
        # Refine fit for this specific period
        K_guess = np.std(rv)
        e_guess = 0.1
        omega_guess = 0.0
        T0_guess = t[0]
        
        # Use the best_params_init if available and close to this P, otherwise use guesses
        if best_params_init is not None:
            # If the best init is close to this P, use it as a better starting point
            if abs(best_params_init[0] - P) < 2.0:
                init_params = best_params_init
            else:
                init_params = [P, K_guess, e_guess, omega_guess, T0_guess]
        else:
            init_params = [P, K_guess, e_guess, omega_guess, T0_guess]

        res = minimize(
            residual_sum_sq_full,
            init_params,
            args=(t, rv, sigma),
            method='Nelder-Mead',
            options={'maxiter': 5000}
        )
        
        if res.success:
            P_opt, K_opt, e_opt, omega_opt, T0_opt = res.x
            # Sanity checks
            if P_opt < 0.5 or P_opt > 200: continue
            if K_opt < 0.1: continue
            
            top_candidates.append({
                'P': P_opt,
                'K': K_opt,
                'e': e_opt,
                'omega': omega_opt,
                'T0': T0_opt,
                'rss': res.fun
            })
    
    # Sort by RSS
    top_candidates.sort(key=lambda x: x['rss'])
    
    # Step 4: Convert to Physical Parameters
    # Assume Solar Mass Star (M_star = 1.989e30 kg)
    # K in m/s, P in days -> seconds
    G = 6.67430e-11
    M_sun = 1.989e30
    M_jup = 1.898e27
    
    planets = []
    if top_candidates:
        best = top_candidates[0]
        P_days = best['P']
        K_ms = best['K']
        e = best['e']
        omega = best['omega']
        T0 = best['T0']
        
        # Calculate m sin i
        # K = (2*pi*G / P)^(1/3) * (m sin i) / (M_star + m sin i)^(2/3) * 1/sqrt(1-e^2)
        # Approximation for m << M_star:
        # m sin i = K * (P * M_star^2 / (2*pi*G))^(1/3) * sqrt(1-e^2)
        
        P_sec = P_days * 86400.0
        # m_sin_i in kg
        m_sin_i_kg = K_ms * (P_sec * M_sun**2 / (2 * np.pi * G))**(1/3) * np.sqrt(1 - e**2)
        m_sin_i_mjup = m_sin_i_kg / M_jup
        
        # Mean longitude l = n * (t - T0) + omega? 
        # Usually l = M + omega. At t=0? Or mean anomaly at epoch?
        # Let's define l_rad as the mean longitude at t=0
        n = 2 * np.pi / P_days
        M0 = n * (0 - T0)
        l_rad = (M0 + omega) % (2 * np.pi)
        
        planets.append({
            "P_days": float(P_days),
            "m_sin_i_mjup": float(m_sin_i_mjup),
            "e": float(e),
            "omega_rad": float(omega),
            "l_rad": float(l_rad)
        })
    
    # Step 5: Output Formatting
    submission = {
        "planets": planets
    }
    
    with open('agent_submission.json', 'w') as f:
        json.dump(submission, f, indent=2)
    
    # Diagnostics
    diagnostics = {
        "top_candidates": top_candidates[:3],
        "num_observations": len(t),
        "period_range_searched": [1.0, 100.0]
    }
    with open('agent_diagnostics.json', 'w') as f:
        json.dump(diagnostics, f, indent=2)

if __name__ == "__main__":
    main()