"""Efficient-frontier grid calculations for the four-fund mandate."""
from __future__ import annotations

import pandas as pd

from mandate import FUNDS, GRID_STEP
from portfolio import portfolio_metrics


def all_long_only_mixes(step: float = GRID_STEP):
    """Yield every four-fund long-only mix on the five percentage point grid."""
    units = round(1 / step)
    for a in range(units + 1):
        for b in range(units - a + 1):
            for c in range(units - a - b + 1):
                yield (a * step, b * step, c * step, (units - a - b - c) * step)


def evaluate_frontier(estimates: dict, checker) -> pd.DataFrame:
    """Return risk, return, weights, and mandate status for all 1,771 grid mixes."""
    rows = []
    for weights in all_long_only_mixes():
        expected, volatility = portfolio_metrics(weights, estimates)
        rules = checker(weights, expected)
        rows.append({**dict(zip(FUNDS, weights)), "expected_return": expected,
                     "volatility": volatility, "meets_mandate": all(rule["pass"] for rule in rules)})
    return pd.DataFrame(rows)
