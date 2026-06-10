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

def keplerian_rv(t, P, K, e, omega, T0):
    # t in days, P in days, K in m/s, e dimensionless, omega in rad
    # T0 is time of periastron passage in days
    # Mean anomaly
    n = 2 * np.pi / P
    M = n * (t - T0)
    # Solve Kepler's equation for E (Eccentric anomaly)
    # M = E - e * sin(E)
    # Use Newton-Raphson
    E = M
    for _ in range(10):
        f = E - e * np.sin(E) - M
        df = 1 - e * np.cos(E)
        if np.abs(df) < 1e-12:
            break
        E = E - f / df
    # True anomaly
    nu = 2 * np.arctan2(np.sqrt(1 + e) * np.sin(E / 2), np.sqrt(1 - e) * np.cos(E / 2))
    # RV
    rv = K * (np.cos(nu + omega) + e * np.cos(omega))
    return rv

def weighted_residuals(params, t, rv, sigma):
    P, K, e, omega, T0 = params
    # Bounds check to avoid NaNs
    if P <= 0 or e < 0 or e >= 1 or K < 0:
        return 1e10
    model = keplerian_rv(t, P, K, e, omega, T0)
    residuals = (rv - model) / sigma
    return np.sum(residuals**2)

def compute_bic(chi2_val, n_params, n_data):
    return n_data * np.log(chi2_val / n_data) + n_params * np.log(n_data)

def is_alias(P1, P2, tolerance=0.05):
    """
    Check if P1 and P2 are likely aliases (e.g., 1/P1 +/- 1/P2 ~ 1 day).
    Common aliases: P, P/2, P/3, 1/(1/P +/- 1).
    We check if 1/P1 - 1/P2 is close to an integer (daily sampling alias).
    """
    if P1 <= 0 or P2 <= 0:
        return False
    freq1 = 1.0 / P1
    freq2 = 1.0 / P2
    diff = abs(freq1 - freq2)
    # Check if difference is close to an integer (1, 2, 3...)
    # This corresponds to daily aliases if sampling is daily.
    # We check if diff is close to an integer within tolerance.
    # Also check if P1 is close to P2 * k or P2 / k
    for k in range(1, 10):
        if abs(P1 - P2 * k) < tolerance * P2:
            return True
        if abs(P2 - P1 * k) < tolerance * P1:
            return True
    
    # Check frequency difference
    # Reduced tolerance for daily alias check (0.01 day^-1 instead of 0.1)
    if abs(diff - round(diff)) < 0.01: 
        return True
        
    return False

def search_planets(times, rvs, sigmas):
    # Precompute weights
    weights = 1.0 / (sigmas**2)
    
    # Period search range: 1 day to 1000 days
    periods = np.logspace(np.log10(1.0), np.log10(1000.0), 2000)
    
    best_score = np.inf
    best_params = None
    candidates = []
    
    top_candidates = []
    
    for P in periods:
        # Fit sinusoid: rv = K * cos(2pi/P * (t - T0)) + offset
        # Linearize: rv = A * cos(wt) + B * sin(wt) + C
        w = 2 * np.pi / P
        cos_wt = np.cos(w * times)
        sin_wt = np.sin(w * times)
        
        # Design matrix
        X = np.vstack([cos_wt, sin_wt, np.ones_like(times)]).T
        # Weighted least squares
        W = np.diag(weights)
        try:
            # Solve (X^T W X) x = X^T W y
            XtW = X.T @ W
            XtWX = XtW @ X
            XtWy = XtW @ rvs
            sol = np.linalg.solve(XtWX, XtWy)
            A, B, C = sol
            K_init = np.sqrt(A**2 + B**2)
            # Phase
            if K_init > 0:
                T0_init = (np.arctan2(B, A) * P) / (2 * np.pi)
                # Normalize T0 to [0, P)
                T0_init = T0_init % P
            else:
                T0_init = 0
            
            # Initial chi2
            model_init = A * cos_wt + B * sin_wt + C
            chi2_init = np.sum(weights * (rvs - model_init)**2)
            
            # Only proceed if significant improvement over constant
            # Constant model chi2
            mean_rv = np.sum(weights * rvs) / np.sum(weights)
            chi2_const = np.sum(weights * (rvs - mean_rv)**2)
            
            if chi2_init < chi2_const:
                # Refine with Keplerian (e=0, omega=0 initially)
                # Params: P, K, e, omega, T0
                
                def obj(params):
                    P_opt, K_opt, e_opt, omega_opt, T0_opt = params
                    if P_opt <= 0 or K_opt < 0 or e_opt < 0 or e_opt >= 1:
                        return 1e10
                    model = keplerian_rv(times, P_opt, K_opt, e_opt, omega_opt, T0_opt)
                    return np.sum(weights * (rvs - model)**2)
                
                # Initial guess
                x0 = [P, K_init, 0.0, 0.0, T0_init]
                
                # Bounds
                bounds = [(P*0.9, P*1.1), (0, None), (0, 0.99), (0, 2*np.pi), (0, P)]
                
                try:
                    res = minimize(obj, x0, method='L-BFGS-B', bounds=bounds)
                    if res.success:
                        P_opt, K_opt, e_opt, omega_opt, T0_opt = res.x
                        chi2_val = res.fun
                        # BIC
                        n_params = 5
                        n_data = len(times)
                        bic_val = compute_bic(chi2_val, n_params, n_data)
                        
                        top_candidates.append({
                            'P': P_opt,
                            'K': K_opt,
                            'e': e_opt,
                            'omega': omega_opt,
                            'T0': T0_opt,
                            'chi2': chi2_val,
                            'bic': bic_val,
                            'K_init': K_init
                        })
                except Exception:
                    pass
        except Exception:
            pass

    # Sort by BIC
    top_candidates.sort(key=lambda x: x['bic'])
    
    # Robust alias filtering
    # We want to avoid selecting a period that is an alias of a longer period.
    # Strategy:
    # 1. Identify the best candidate.
    # 2. Check if there exists a candidate with a longer period (P_long) such that:
    #    a) P_long is not an alias of P_best (or vice versa, but we prefer longer).
    #    b) P_best is an alias of P_long.
    #    c) The BIC of P_long is within a reasonable threshold (e.g., 10) of P_best.
    # 3. If such a P_long exists, prefer P_long.
    # 4. Also, if P_best is < 1.5 days, be very suspicious.
    
    final_candidates = []
    
    # Fallback: If no candidates found via strict filtering, return the best sinusoid fit
    # to ensure we don't return an empty list if a signal exists but refinement failed.
    if len(top_candidates) == 0:
        # If top_candidates is empty, we try to find the best sinusoid fit directly
        # and return it as a fallback, assuming e=0, omega=0
        best_P = None
        best_chi2 = np.inf
        best_K = 0
        best_T0 = 0
        
        for P in periods:
            w = 2 * np.pi / P
            cos_wt = np.cos(w * times)
            sin_wt = np.sin(w * times)
            X = np.vstack([cos_wt, sin_wt, np.ones_like(times)]).T
            W = np.diag(weights)
            try:
                XtW = X.T @ W
                XtWX = XtW @ X
                XtWy = XtW @ rvs
                sol = np.linalg.solve(XtWX, XtWy)
                A, B, C = sol
                K_val = np.sqrt(A**2 + B**2)
                if K_val > 0:
                    T0_val = (np.arctan2(B, A) * P) / (2 * np.pi)
                    T0_val = T0_val % P
                    model_init = A * cos_wt + B * sin_wt + C
                    chi2_val = np.sum(weights * (rvs - model_init)**2)
                    mean_rv = np.sum(weights * rvs) / np.sum(weights)
                    chi2_const = np.sum(weights * (rvs - mean_rv)**2)
                    
                    if chi2_val < chi2_const and chi2_val < best_chi2:
                        best_chi2 = chi2_val
                        best_P = P
                        best_K = K_val
                        best_T0 = T0_val
            except:
                pass
        
        if best_P is not None:
            # Create a fallback candidate
            fallback = {
                'P': best_P,
                'K': best_K,
                'e': 0.0,
                'omega': 0.0,
                'T0': best_T0,
                'chi2': best_chi2,
                'bic': compute_bic(best_chi2, 5, len(times)),
                'K_init': best_K
            }
            top_candidates.append(fallback)
            top_candidates.sort(key=lambda x: x['bic'])

    if len(top_candidates) > 0:
        best = top_candidates[0]
        selected = best
        
        # Collect all valid candidates that could be the "true" period
        # A valid candidate is one that:
        # 1. Is an alias of the current best (or best is an alias of it)
        # 2. Has a longer period (usually the true period is longer than the alias)
        # 3. Has a BIC within a threshold of the best
        valid_alternatives = []
        
        for cand in top_candidates:
            if cand is best:
                continue
            
            # Check if best is an alias of cand (cand is the potential parent)
            # We look for cand where cand['P'] > best['P'] and they are aliases
            if is_alias(best['P'], cand['P']):
                if cand['P'] > best['P'] and cand['bic'] < best['bic'] + 10:
                    valid_alternatives.append(cand)
            
            # Also check if best is very short (< 1.5 days) and cand is longer with similar BIC
            elif best['P'] < 1.5 and cand['P'] > 1.5 and cand['bic'] < best['bic'] + 10:
                if is_alias(best['P'], cand['P']):
                    valid_alternatives.append(cand)
        
        # If we found valid alternatives, select the one with the lowest BIC
        if valid_alternatives:
            # Sort valid alternatives by BIC and pick the best one
            valid_alternatives.sort(key=lambda x: x['bic'])
            selected = valid_alternatives[0]
        
        # Additional check: If selected is still < 1.0 days, and there is a candidate > 1.0 days
        # with BIC within 5, pick the longer one.
        if selected['P'] < 1.0:
            best_short = selected
            valid_long_candidates = []
            for cand in top_candidates:
                if cand['P'] > 1.0 and cand['bic'] < best_short['bic'] + 5:
                    valid_long_candidates.append(cand)
            
            if valid_long_candidates:
                valid_long_candidates.sort(key=lambda x: x['bic'])
                selected = valid_long_candidates[0]
        
        final_candidates.append(selected)
    
    return final_candidates

def calculate_mass(P_days, K_ms, e, M_star_msun=1.0):
    # P in days, K in m/s, e dimensionless, M_star in solar masses
    # M sin i = K * (P * (1-e^2)^0.5)^(1/3) * (M_star)^(2/3) / (2*pi*G)^(1/3)
    # Simplified formula for M sin i in Jupiter masses:
    # M_sin_i (Mjup) = 4.919e-3 * K (m/s) * P (days)^(1/3) * (1-e^2)^(1/2) * (M_star/Msun)^(2/3)
    
    G = 6.67430e-11
    M_sun_kg = 1.98847e30
    M_jup_kg = 1.89813e27
    
    P_sec = P_days * 86400.0
    M_star_kg = M_star_msun * M_sun_kg
    
    # M_p sin i = K * (P / (2*pi*G))^(1/3) * M_star^(2/3) * sqrt(1-e^2)
    term1 = K_ms * (P_sec / (2 * np.pi * G))**(1/3)
    term2 = (M_star_kg)**(2/3)
    term3 = np.sqrt(1 - e**2)
    
    M_p_sin_i_kg = term1 * term2 * term3
    M_p_sin_i_mjup = M_p_sin_i_kg / M_jup_kg
    
    return M_p_sin_i_mjup

def main():
    times, rvs, sigmas, instruments = load_data('stargazer_observations.json')
    
    candidates = search_planets(times, rvs, sigmas)
    
    planets = []
    for cand in candidates:
        P_days = cand['P']
        K_ms = cand['K']
        e = cand['e']
        omega = cand['omega']
        T0 = cand['T0']
        
        # Calculate mass
        M_p_sin_i_mjup = calculate_mass(P_days, K_ms, e, M_star_msun=1.0)
        
        # l_rad: mean longitude at epoch (t=0)
        # l(t) = 2pi/P * (t - T0) + omega
        # At t=0, l0 = -2pi/P * T0 + omega
        l0 = (-2 * np.pi / P_days) * T0 + omega
        # Normalize to [0, 2pi)
        l0 = l0 % (2 * np.pi)
        
        planet = {
            "P_days": float(P_days),
            "m_sin_i_mjup": float(M_p_sin_i_mjup),
            "e": float(e),
            "omega_rad": float(omega),
            "l_rad": float(l0)
        }
        planets.append(planet)
    
    output = {"planets": planets}
    
    with open('agent_submission.json', 'w') as f:
        json.dump(output, f, indent=2)
    
    # Diagnostics
    diag = {
        "top_candidates": candidates,
        "num_observations": len(times),
        "period_range_searched": [1.0, 1000.0]
    }
    with open('agent_diagnostics.json', 'w') as f:
        json.dump(diag, f, indent=2)

if __name__ == "__main__":
    main()