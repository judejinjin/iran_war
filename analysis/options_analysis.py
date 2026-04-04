"""
Options Analytics — Black-76 pricing, Greeks, vol surface, Breeden-Litzenberger.

Provides:
- Black-76 option pricing for futures options
- Full Greeks computation (delta, gamma, vega, theta, rho)
- Vol surface construction (ATM vol, 25-delta skew, butterfly)
- Breeden-Litzenberger risk-neutral probability extraction
"""

import math
from datetime import date, datetime
from typing import Optional

import numpy as np
from scipy.stats import norm
from scipy.interpolate import CubicSpline
from loguru import logger

from db.database import get_session, OptionsChain, VolSurface


# ─── Black-76 Model ──────────────────────────────────────────────────────────

def black76_price(F: float, K: float, T: float, r: float, sigma: float,
                  option_type: str = "CALL") -> float:
    """
    Black-76 futures option price.

    Args:
        F: Futures price (underlying)
        K: Strike price
        T: Time to expiry in years
        r: Risk-free rate (annualized)
        sigma: Implied volatility (annualized)
        option_type: "CALL" or "PUT"

    Returns:
        Option price.
    """
    if T <= 0 or sigma <= 0:
        # Intrinsic value only
        if option_type == "CALL":
            return max(0, F - K)
        return max(0, K - F)

    d1 = (math.log(F / K) + 0.5 * sigma ** 2 * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    discount = math.exp(-r * T)

    if option_type == "CALL":
        return discount * (F * norm.cdf(d1) - K * norm.cdf(d2))
    else:
        return discount * (K * norm.cdf(-d2) - F * norm.cdf(-d1))


def black76_greeks(F: float, K: float, T: float, r: float, sigma: float,
                   option_type: str = "CALL") -> dict:
    """
    Compute all Black-76 Greeks.

    Returns:
        dict with delta, gamma, vega, theta, rho.
    """
    if T <= 0 or sigma <= 0:
        intrinsic = max(0, F - K) if option_type == "CALL" else max(0, K - F)
        itm = (F > K) if option_type == "CALL" else (K > F)
        return {
            "delta": (1.0 if itm else 0.0) * (1 if option_type == "CALL" else -1),
            "gamma": 0.0,
            "vega": 0.0,
            "theta": 0.0,
            "rho": 0.0,
            "price": intrinsic,
        }

    sqrt_T = math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * sigma ** 2 * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    discount = math.exp(-r * T)

    # Price
    if option_type == "CALL":
        price = discount * (F * norm.cdf(d1) - K * norm.cdf(d2))
        delta = discount * norm.cdf(d1)
    else:
        price = discount * (K * norm.cdf(-d2) - F * norm.cdf(-d1))
        delta = -discount * norm.cdf(-d1)

    # Gamma (same for call/put)
    gamma = discount * norm.pdf(d1) / (F * sigma * sqrt_T)

    # Vega (per 1% move → divide by 100)
    vega = F * discount * norm.pdf(d1) * sqrt_T / 100.0

    # Theta (per day → divide by 365)
    if option_type == "CALL":
        theta = (
            -F * discount * norm.pdf(d1) * sigma / (2 * sqrt_T)
            + r * discount * (F * norm.cdf(d1) - K * norm.cdf(d2))
        ) / 365.0
    else:
        theta = (
            -F * discount * norm.pdf(d1) * sigma / (2 * sqrt_T)
            - r * discount * (K * norm.cdf(-d2) - F * norm.cdf(-d1))
        ) / 365.0

    # Rho
    if option_type == "CALL":
        rho = -T * price / 100.0
    else:
        rho = -T * price / 100.0

    return {
        "delta": delta,
        "gamma": gamma,
        "vega": vega,
        "theta": theta,
        "rho": rho,
        "price": price,
    }


def implied_vol(F: float, K: float, T: float, r: float, market_price: float,
                option_type: str = "CALL", tol: float = 1e-6,
                max_iter: int = 100) -> Optional[float]:
    """
    Newton-Raphson implied volatility solver for Black-76.

    Returns:
        Implied volatility, or None if not converged.
    """
    if T <= 0 or market_price <= 0:
        return None

    # Intrinsic check
    intrinsic = max(0, F - K) if option_type == "CALL" else max(0, K - F)
    if market_price < intrinsic:
        return None

    sigma = 0.3  # Initial guess
    for _ in range(max_iter):
        price = black76_price(F, K, T, r, sigma, option_type)
        diff = price - market_price

        if abs(diff) < tol:
            return sigma

        # Vega for Newton step
        sqrt_T = math.sqrt(T)
        d1 = (math.log(F / K) + 0.5 * sigma ** 2 * T) / (sigma * sqrt_T)
        vega = F * math.exp(-r * T) * norm.pdf(d1) * sqrt_T

        if vega < 1e-12:
            break

        sigma -= diff / vega
        sigma = max(0.01, min(5.0, sigma))  # Clamp

    return None


# ─── Vol Surface Construction ────────────────────────────────────────────────

def compute_vol_surface_metrics(underlying: str, target_date: date,
                                 futures_price: float,
                                 r: float = 0.05) -> list[dict]:
    """
    Compute vol surface metrics (ATM vol, 25-delta skew, butterfly) for each expiry.

    Reads options_chains from DB, computes metrics, stores in vol_surface table.

    Returns: list of metric dicts per expiry.
    """
    session = get_session()
    try:
        chains = session.query(OptionsChain).filter(
            OptionsChain.date == target_date,
            OptionsChain.underlying == underlying,
        ).all()

        if not chains:
            return []

        # Group by expiry
        by_expiry = {}
        for c in chains:
            key = c.expiry_date
            if key not in by_expiry:
                by_expiry[key] = []
            by_expiry[key].append(c)

        results = []
        for expiry_date, options in by_expiry.items():
            T = max(1, (expiry_date - target_date).days) / 365.0

            # Find ATM vol (closest to futures price)
            calls = [o for o in options if o.option_type == "CALL" and o.implied_vol]
            puts = [o for o in options if o.option_type == "PUT" and o.implied_vol]

            if not calls:
                continue

            # ATM vol: average of ATM call and put IV
            atm_call = min(calls, key=lambda o: abs(o.strike - futures_price))
            atm_vol = atm_call.implied_vol

            atm_put = min(puts, key=lambda o: abs(o.strike - futures_price)) if puts else None
            if atm_put and atm_put.implied_vol:
                atm_vol = (atm_vol + atm_put.implied_vol) / 2.0

            # 25-delta skew: IV(25d put) - IV(25d call)
            skew_25d = None
            butterfly_25d = None

            # Find 25-delta call and put
            call_25d = None
            put_25d = None
            for c in calls:
                greeks = black76_greeks(futures_price, c.strike, T, r, c.implied_vol, "CALL")
                if abs(greeks["delta"] - 0.25) < 0.10:
                    if call_25d is None or abs(greeks["delta"] - 0.25) < abs(call_25d[1] - 0.25):
                        call_25d = (c, greeks["delta"])

            for p in puts:
                greeks = black76_greeks(futures_price, p.strike, T, r, p.implied_vol, "PUT")
                if abs(greeks["delta"] + 0.25) < 0.10:
                    if put_25d is None or abs(greeks["delta"] + 0.25) < abs(put_25d[1] + 0.25):
                        put_25d = (p, greeks["delta"])

            if call_25d and put_25d:
                skew_25d = put_25d[0].implied_vol - call_25d[0].implied_vol
                butterfly_25d = (put_25d[0].implied_vol + call_25d[0].implied_vol) / 2.0 - atm_vol

            # Store in vol_surface
            existing = session.query(VolSurface).filter(
                VolSurface.date == target_date,
                VolSurface.underlying == underlying,
                VolSurface.expiry_date == expiry_date,
            ).first()

            data = {
                "atm_vol": atm_vol,
                "skew_25d": skew_25d,
                "smile_25d": butterfly_25d,
            }

            if existing:
                for k, v in data.items():
                    setattr(existing, k, v)
            else:
                session.add(VolSurface(
                    date=target_date,
                    underlying=underlying,
                    expiry_date=expiry_date,
                    **data,
                ))

            results.append({
                "expiry": expiry_date,
                "atm_vol": atm_vol,
                "skew_25d": skew_25d,
                "butterfly_25d": butterfly_25d,
                "T": T,
            })

        session.commit()
        logger.info(f"Vol surface: {len(results)} expiries for {underlying} on {target_date}")
        return results

    except Exception as e:
        session.rollback()
        logger.error(f"Vol surface computation failed: {e}")
        raise
    finally:
        session.close()


# ─── Breeden-Litzenberger Risk-Neutral Distribution ─────────────────────────

def breeden_litzenberger(
    strikes: np.ndarray,
    call_prices: np.ndarray,
    F: float,
    T: float,
    r: float = 0.05,
    n_points: int = 200,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Extract risk-neutral probability density from call prices using
    Breeden-Litzenberger (1978): f(K) = e^(rT) * d²C/dK²

    Args:
        strikes: Array of strike prices (sorted ascending)
        call_prices: Corresponding call option prices
        F: Current futures price
        T: Time to expiry in years
        r: Risk-free rate
        n_points: Number of interpolation points

    Returns:
        (strike_grid, pdf): Arrays of strikes and probability density.
    """
    if len(strikes) < 4:
        return np.array([]), np.array([])

    # Sort by strike
    sort_idx = np.argsort(strikes)
    K = strikes[sort_idx]
    C = call_prices[sort_idx]

    # Remove non-monotonic prices
    valid = np.ones(len(C), dtype=bool)
    for i in range(1, len(C)):
        if C[i] >= C[i - 1]:
            valid[i] = False
    K = K[valid]
    C = C[valid]

    if len(K) < 4:
        return np.array([]), np.array([])

    # Cubic spline interpolation
    try:
        cs = CubicSpline(K, C)
    except Exception:
        return np.array([]), np.array([])

    # Fine grid
    K_fine = np.linspace(K[0], K[-1], n_points)

    # Second derivative
    d2C_dK2 = cs(K_fine, 2)

    # Risk-neutral PDF
    pdf = np.exp(r * T) * d2C_dK2

    # Clip negative values (numerical artifacts)
    pdf = np.maximum(pdf, 0)

    # Normalize to integrate to ~1
    total = np.trapz(pdf, K_fine)
    if total > 0:
        pdf = pdf / total

    return K_fine, pdf


def market_implied_scenario_probs(
    strikes: np.ndarray,
    call_prices: np.ndarray,
    F: float,
    T: float,
    scenarios: list[dict],
    r: float = 0.05,
) -> dict[str, float]:
    """
    Map risk-neutral distribution to scenario probabilities.

    Integrates the Breeden-Litzenberger PDF over each scenario's Brent price range.

    Args:
        strikes, call_prices: Options chain data.
        F: Futures price.
        T: Time to expiry.
        scenarios: List of scenario dicts with name, brent_low, brent_high.
        r: Risk-free rate.

    Returns:
        Dict mapping scenario name to market-implied probability.
    """
    K_grid, pdf = breeden_litzenberger(strikes, call_prices, F, T, r)

    if len(K_grid) == 0:
        return {s["name"]: 1.0 / len(scenarios) for s in scenarios}

    probs = {}
    for s in scenarios:
        low = s["brent_low"]
        high = s["brent_high"]

        # Find indices within range
        mask = (K_grid >= low) & (K_grid <= high)
        if mask.any():
            prob = np.trapz(pdf[mask], K_grid[mask])
        else:
            prob = 0.0

        probs[s["name"]] = float(prob)

    # Normalize
    total = sum(probs.values())
    if total > 0:
        probs = {k: v / total for k, v in probs.items()}

    return probs


def compute_greeks_for_chain(underlying: str, target_date: date,
                              futures_price: float, r: float = 0.05) -> int:
    """
    Compute Black-76 Greeks for all options in the chain for a given date.
    Updates options_chains rows with delta, gamma, vega, theta.

    Returns: number of options updated.
    """
    session = get_session()
    try:
        options = session.query(OptionsChain).filter(
            OptionsChain.date == target_date,
            OptionsChain.underlying == underlying,
        ).all()

        updated = 0
        for opt in options:
            if not opt.implied_vol or opt.implied_vol <= 0:
                continue

            T = max(1, (opt.expiry_date - target_date).days) / 365.0
            greeks = black76_greeks(
                futures_price, opt.strike, T, r, opt.implied_vol, opt.option_type
            )

            opt.delta = greeks["delta"]
            opt.gamma = greeks["gamma"]
            opt.vega = greeks["vega"]
            opt.theta = greeks["theta"]
            updated += 1

        session.commit()
        logger.info(f"Updated Greeks for {updated} options ({underlying} on {target_date})")
        return updated

    except Exception as e:
        session.rollback()
        logger.error(f"Greeks computation failed: {e}")
        raise
    finally:
        session.close()
