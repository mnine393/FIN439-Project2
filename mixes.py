"""Shared vectorized statistics for Compass's five-percentage-point mixes."""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from mandate import GRID_STEP


@lru_cache(maxsize=64)
def mix_matrix(fund_count: int = 4, step: float = GRID_STEP) -> np.ndarray:
    """Return all long-only grid mixes, retaining the legacy four-fund ordering."""
    if not 2 <= fund_count <= 8:
        raise ValueError("A mix grid supports from 2 to 8 holdings.")
    units = round(1 / step)
    rows = []
    def append(prefix, remaining, places):
        if places == 1:
            rows.append(tuple(prefix + [remaining]))
            return
        for value in range(remaining + 1):
            append(prefix + [value], remaining - value, places - 1)
    append([], units, fund_count)
    return np.asarray(rows, dtype=float) * step


@lru_cache(maxsize=1)
def all_mix_matrix() -> np.ndarray:
    """Return grid mixes in the original nested-loop order."""
    return mix_matrix(4, GRID_STEP)


_statistics_cache: dict[tuple[tuple[int, int], bytes], dict[str, np.ndarray]] = {}


def mix_statistic(monthly_returns: pd.DataFrame | np.ndarray, weights) -> tuple[float, float, float]:
    """Calculate the three mix statistics for one allocation at a time."""
    values = np.asarray(monthly_returns, dtype=float)
    allocation = np.asarray(weights, dtype=float)
    portfolio_returns = values @ allocation
    expected_return = float(portfolio_returns.mean() * 12)
    volatility = float(portfolio_returns.std(ddof=1) * np.sqrt(12))
    if len(portfolio_returns) >= 12:
        rolling = np.array([np.prod(1 + portfolio_returns[index:index + 12]) - 1
                            for index in range(len(portfolio_returns) - 11)])
        worst_return = float(rolling.min())
    else:
        worst_return = float(np.prod(1 + portfolio_returns) - 1)
    return expected_return, volatility, worst_return


def mix_statistics(monthly_returns: pd.DataFrame | np.ndarray, step: float = GRID_STEP) -> dict[str, np.ndarray]:
    """Calculate expected return, volatility, and worst rolling-year return for all mixes."""
    values = np.asarray(monthly_returns, dtype=float)
    key = (values.shape, values.tobytes(), step)
    cached = _statistics_cache.get(key)
    if cached is not None:
        return cached
    weights = mix_matrix(values.shape[1], step)
    expected_returns = values.mean(axis=0) @ weights.T * 12
    covariance = np.cov(values, rowvar=False, ddof=1)
    variances = np.einsum("ij,jk,ik->i", weights, covariance, weights) * 12
    volatility = np.sqrt(np.maximum(variances, 0.0))
    portfolio_returns = values @ weights.T
    log_returns = np.log1p(portfolio_returns)
    if len(values) >= 12:
        cumulative = np.vstack((np.zeros((1, len(weights))), np.cumsum(log_returns, axis=0)))
        rolling_returns = np.exp(cumulative[12:] - cumulative[:-12]) - 1
        worst_returns = rolling_returns.min(axis=0)
    else:
        worst_returns = np.prod(1 + portfolio_returns, axis=0) - 1
    result = {
        "weights": weights,
        "expected_return": expected_returns,
        "volatility": volatility,
        "worst_12_month_return": worst_returns,
    }
    _statistics_cache[key] = result
    return result


def first_lowest_volatility(mask: np.ndarray, statistics: dict[str, np.ndarray]) -> int | None:
    """Return the first lowest-volatility feasible grid row, preserving tie behavior."""
    indexes = np.flatnonzero(mask)
    if len(indexes) == 0:
        return None
    return int(indexes[np.argmin(statistics["volatility"][indexes])])
