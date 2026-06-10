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
    instruments = obs.get('instruments', [''] * len(times))
    return times, rvs, sigmas, instruments

def keplerian_rv(t, P, K, e, omega, l0, T0):
    # t in days, P in days, K in m/s, e dimensionless, omega in rad, l0 in rad
    # T0 is time of periastron passage in days
    # Mean anomaly
    M = 2 * np.pi * (t - T0) / P
    # Solve Kepler's equation for Eccentric anomaly E
    # E - e*sin(E) = M
    # Use Newton-Raphson
    E = M
    for _ in range(10):
        denom = 1 - e * np.cos(E)
        # Avoid division by zero if e is close to 1 and cos(E) is close to 1/e
        if np.abs(denom) < 1e-10:
            denom = 1e-10
        E = E - (E - e * np.sin(E) - M) / denom
    # True anomaly
    nu = 2 * np.arctan2(np.sqrt(1 + e) * np.sin(E / 2), np.sqrt(1 - e) * np.cos(E / 2))
    # RV
    rv = K * (np.cos(nu + omega) + e * np.cos(omega))
    return rv

def residual_sum_sq(params, t, rv, sigma):
    P, K, e, omega, T0 = params
    # Bounds checks to avoid NaNs
    if P <= 0 or K < 0 or e < 0 or e >= 1:
        return 1e10
    model = keplerian_rv(t, P, K, e, omega, 0, T0)
    res = (rv - model) / sigma
    return np.sum(res**2)

def calculate_m_sin_i(P_days, K_ms, M_star_msun=1.0, e=0.0):
    # P in days, K in m/s, M_star in solar masses
    # G = 6.67430e-11 m^3 kg^-1 s^-2
    # M_sun = 1.98847e30 kg
    # M_jup = 1.89813e27 kg
    # Formula: m sin i = (K * P^(1/3) * M_star^(2/3)) / ( (2*pi*G)^(1/3) ) * sqrt(1-e^2)
    P_sec = P_days * 86400.0
    G = 6.67430e-11
    M_sun_kg = 1.98847e30
    M_jup_kg = 1.89813e27
    M_star_kg = M_star_msun * M_sun_kg
    
    # m sin i in kg
    m_sin_i_kg = K_ms * (P_sec / (2 * np.pi * G))**(1/3) * (M_star_kg)**(2/3) * np.sqrt(1 - e**2)
    # Convert to Jupiter masses
    m_sin_i_mjup = m_sin_i_kg / M_jup_kg
    return m_sin_i_mjup

def run_periodogram(t, rv, sigma):
    # Simple Lomb-Scargle-like power calculation or just grid search
    # We will do a grid search over periods and fit a simple sinusoid first to find candidates
    # Period range: 1 day to 1000 days
    periods = np.logspace(np.log10(1.0), np.log10(1000.0), 2000)
    powers = []
    
    # Pre-compute weights to avoid creating large diagonal matrices
    # w = 1 / sigma^2
    # Handle potential zero sigma by setting a minimum value or masking
    # If sigma is 0, weight is infinite. We'll cap it or skip.
    # Assuming sigma > 0 for valid data. If 0, set to a very small number to avoid inf.
    sigma_safe = np.where(sigma == 0, 1e-9, sigma)
    w = 1.0 / (sigma_safe ** 2)
    
    for P in periods:
        # Fit simple sinusoid: A * cos(2*pi*t/P + phi) + C
        # Linear least squares for A, phi, C
        # y = A cos(wt) + B sin(wt) + C
        w_val = 2 * np.pi / P
        cos_term = np.cos(w_val * t)
        sin_term = np.sin(w_val * t)
        
        # Weighted least squares without explicit matrix construction
        # We need to solve (X^T W X) beta = X^T W y
        # X is [cos, sin, 1]
        # W is diagonal with elements w
        
        # Compute X^T W X (3x3)
        # Row 0: [sum(w*cos^2), sum(w*cos*sin), sum(w*cos)]
        # Row 1: [sum(w*sin*cos), sum(w*sin^2), sum(w*sin)]
        # Row 2: [sum(w*cos), sum(w*sin), sum(w)]
        
        wc = w * cos_term
        ws = w * sin_term
        
        XTX_00 = np.sum(wc * cos_term)
        XTX_01 = np.sum(wc * sin_term)
        XTX_02 = np.sum(wc)
        
        XTX_11 = np.sum(ws * sin_term)
        XTX_12 = np.sum(ws)
        
        XTX_22 = np.sum(w)
        
        # Matrix is symmetric
        XtWX = np.array([
            [XTX_00, XTX_01, XTX_02],
            [XTX_01, XTX_11, XTX_12],
            [XTX_02, XTX_12, XTX_22]
        ])
        
        # Compute X^T W y (3x1)
        # Row 0: sum(w * cos * y)
        # Row 1: sum(w * sin * y)
        # Row 2: sum(w * y)
        
        Xty_0 = np.sum(wc * rv)
        Xty_1 = np.sum(ws * rv)
        Xty_2 = np.sum(w * rv)
        
        XtWy = np.array([Xty_0, Xty_1, Xty_2])
        
        try:
            beta = np.linalg.solve(XtWX, XtWy)
        except np.linalg.LinAlgError:
            powers.append(0)
            continue
            
        A = np.sqrt(beta[0]**2 + beta[1]**2)
        
        # Calculate RSS
        model = beta[0] * cos_term + beta[1] * sin_term + beta[2]
        res = (rv - model) / sigma_safe
        rss = np.sum(res**2)
        
        # Lower RSS is better. We want to maximize power (minimize RSS)
        powers.append(-rss) # Negative RSS so max is best
    
    powers = np.array(powers)
    # Find top candidates
    indices = np.argsort(powers)[::-1]
    
    candidates = []
    for idx in indices[:20]:
        P = periods[idx]
        power = powers[idx]
        candidates.append((P, power))
    
    # Filter aliases
    final_candidates = []
    for P, power in candidates:
        is_harmonic = False
        for P_ref, _ in final_candidates:
            # Check if P is approx integer multiple or fraction of P_ref
            ratio = P / P_ref
            if abs(ratio - round(ratio)) < 0.05 and round(ratio) != 1:
                is_harmonic = True
                break
            ratio = P_ref / P
            if abs(ratio - round(ratio)) < 0.05 and round(ratio) != 1:
                is_harmonic = True
                break
        if not is_harmonic:
            final_candidates.append((P, power))
        if len(final_candidates) >= 5:
            break
            
    return final_candidates

def fit_keplerian(t, rv, sigma, P_init):
    # Initial guess: K from sinusoid fit, e=0, omega=0, T0=0
    # Re-fit sinusoid to get K and phase
    w_val = 2 * np.pi / P_init
    cos_term = np.cos(w_val * t)
    sin_term = np.sin(w_val * t)
    
    # Handle zero sigma
    sigma_safe = np.where(sigma == 0, 1e-9, sigma)
    w = 1.0 / (sigma_safe ** 2)
    
    wc = w * cos_term
    ws = w * sin_term
    
    XTX_00 = np.sum(wc * cos_term)
    XTX_01 = np.sum(wc * sin_term)
    XTX_02 = np.sum(wc)
    XTX_11 = np.sum(ws * sin_term)
    XTX_12 = np.sum(ws)
    XTX_22 = np.sum(w)
    
    XtWX = np.array([
        [XTX_00, XTX_01, XTX_02],
        [XTX_01, XTX_11, XTX_12],
        [XTX_02, XTX_12, XTX_22]
    ])
    
    Xty_0 = np.sum(wc * rv)
    Xty_1 = np.sum(ws * rv)
    Xty_2 = np.sum(w * rv)
    XtWy = np.array([Xty_0, Xty_1, Xty_2])
    
    try:
        beta = np.linalg.solve(XtWX, XtWy)
    except:
        return None
        
    K_init = np.sqrt(beta[0]**2 + beta[1]**2)
    
    # Initial params: [P, K, e, omega, T0]
    p0 = [P_init, K_init, 0.0, 0.0, 0.0]
    
    # Bounds
    bounds = [
        (P_init * 0.5, P_init * 2.0), # P
        (0.0, 1000.0), # K
        (0.0, 0.99), # e
        (0.0, 2*np.pi), # omega
        (0.0, P_init) # T0
    ]
    
    try:
        res = minimize(residual_sum_sq, p0, args=(t, rv, sigma), bounds=bounds, method='L-BFGS-B')
        if res.success:
            return res.x, res.fun
        else:
            return None
    except:
        return None

def main():
    # 1. Load Data
    t, rv, sigma, instruments = load_data('stargazer_observations.json')
    
    # 2. Period Search
    candidates = run_periodogram(t, rv, sigma)
    
    diagnostics = {
        "top_candidates": [],
        "best_fit": None
    }
    
    best_score = float('inf')
    best_params = None
    best_P = None
    
    # 3. Fit Keplerian for top candidates
    for P, power in candidates:
        result = fit_keplerian(t, rv, sigma, P)
        if result:
            params, rss = result
            P_fit, K_fit, e_fit, omega_fit, T0_fit = params
            # Calculate BIC or AIC
            # BIC = n * ln(RSS/n) + k * ln(n)
            n = len(t)
            k = 5 # P, K, e, omega, T0
            if rss > 0:
                bic = n * np.log(rss / n) + k * np.log(n)
            else:
                bic = float('inf')
            
            diagnostics["top_candidates"].append({
                "P_days": P_fit,
                "K_ms": K_fit,
                "e": e_fit,
                "omega_rad": omega_fit,
                "T0_days": T0_fit,
                "RSS": rss,
                "BIC": bic
            })
            
            if bic < best_score:
                best_score = bic
                best_params = params
                best_P = P_fit
    
    # 4. Finalize best planet
    if best_params is not None:
        P_best, K_best, e_best, omega_best, T0_best = best_params
        
        # Calculate m sin i using the corrected function with eccentricity
        m_sin_i_mjup = calculate_m_sin_i(P_best, K_best, M_star_msun=1.0, e=e_best)
        
        # Mean longitude l_rad = omega_best (at T0, M=0, l = omega)
        l_rad = omega_best
        
        planet = {
            "P_days": float(P_best),
            "m_sin_i_mjup": float(m_sin_i_mjup),
            "e": float(e_best),
            "omega_rad": float(omega_best),
            "l_rad": float(l_rad)
        }
        
        diagnostics["best_fit"] = planet
    else:
        planet = None
        diagnostics["best_fit"] = None

    # 5. Write Output
    output = {
        "planets": [planet] if planet else []
    }
    
    with open('agent_submission.json', 'w') as f:
        json.dump(output, f, indent=2)
        
    # Write diagnostics
    with open('agent_diagnostics.json', 'w') as f:
        json.dump(diagnostics, f, indent=2)

if __name__ == "__main__":
    main()