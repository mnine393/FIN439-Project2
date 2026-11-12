"""Repeatable seven-year endowment value simulations."""
from __future__ import annotations

import numpy as np
import pandas as pd

from mandate import HORIZON_YEARS, PORTFOLIO_SIZE_DOLLARS, QUARTERLY_PAYOUT_DOLLARS

MONTHS = HORIZON_YEARS * 12


def simulate_portfolio(monthly_returns: pd.DataFrame, weights, objective: float, *, method="Historical bootstrap",
                       seed: int = 439, paths: int = 10_000) -> dict:
    """Simulate portfolio returns and quarterly spending with a deterministic seed."""
    values = monthly_returns.to_numpy(dtype=float)
    weights = np.asarray(weights, dtype=float)
    rng = np.random.default_rng(seed)
    if method == "Historical bootstrap":
        draws = rng.integers(0, len(values), size=(paths, MONTHS))
        path_returns = values[draws] @ weights
    elif method == "Normal distribution":
        path_returns = rng.multivariate_normal(values.mean(axis=0), np.cov(values, rowvar=False), size=(paths, MONTHS)) @ weights
    else:
        raise ValueError("Simulation method must be Historical bootstrap or Normal distribution.")
    before_payout_return = np.prod(1 + path_returns, axis=1) ** (12 / MONTHS) - 1
    dollar_values = np.empty((paths, MONTHS + 1), dtype=float)
    dollar_values[:, 0] = PORTFOLIO_SIZE_DOLLARS
    for month in range(MONTHS):
        dollar_values[:, month + 1] = dollar_values[:, month] * (1 + path_returns[:, month])
        if (month + 1) % 3 == 0:
            dollar_values[:, month + 1] -= QUARTERLY_PAYOUT_DOLLARS
    return {"values": dollar_values, "annualized_returns": before_payout_return,
            "probability_objective": float(np.mean(before_payout_return >= objective)),
            "probability_below_90m": float(np.mean(np.min(dollar_values, axis=1) < 90_000_000)),
            "median_ending_value": float(np.median(dollar_values[:, -1])),
            "p5_ending_value": float(np.percentile(dollar_values[:, -1], 5)),
            "p95_ending_value": float(np.percentile(dollar_values[:, -1], 95))}


def fan_chart_frame(result: dict) -> pd.DataFrame:
    """Summarize simulated dollar paths for an Altair fan chart."""
    values = result["values"]
    return pd.DataFrame({"month": np.arange(values.shape[1]), "p5": np.percentile(values, 5, axis=0),
                         "p25": np.percentile(values, 25, axis=0), "median": np.median(values, axis=0),
                         "p75": np.percentile(values, 75, axis=0), "p95": np.percentile(values, 95, axis=0)})
