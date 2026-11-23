"""Efficient-frontier grid calculations for the four-fund mandate."""
from __future__ import annotations

import pandas as pd

from mandate import FUNDS, GRID_STEP
from portfolio import portfolio_metrics
from mixes import all_mix_matrix, mix_matrix, mix_statistics


def all_long_only_mixes(step: float = GRID_STEP, fund_count: int = 4):
    """Yield every four-fund long-only mix on the five percentage point grid."""
    if step == GRID_STEP and fund_count == 4:
        yield from (tuple(row) for row in all_mix_matrix())
        return
    yield from (tuple(row) for row in mix_matrix(fund_count, step))


def evaluate_frontier(estimates: dict, checker=None, *, mandate=None, inflation=None, tickers=None,
                      step: float = GRID_STEP) -> pd.DataFrame:
    """Return risk, return, weights, and mandate status for all 1,771 grid mixes."""
    if checker is None:
        if mandate is None or inflation is None:
            raise ValueError("Provide a rule checker or a mandate and inflation rate.")
        checker = lambda weights, expected: mandate.check(weights, {"expected_return": expected, "monthly_returns": estimates.get("monthly_returns")}, inflation)
    tickers = tuple(tickers or FUNDS)
    statistics = mix_statistics(estimates["monthly_returns"], step) if "monthly_returns" in estimates else None
    rows = []
    for index, weights in enumerate(all_long_only_mixes(step, len(tickers))):
        if statistics is None:
            expected, volatility = portfolio_metrics(weights, estimates)
        else:
            expected = float(statistics["expected_return"][index])
            volatility = float(statistics["volatility"][index])
        rules = checker(weights, expected)
        worst = None if statistics is None else float(statistics["worst_12_month_return"][index])
        rows.append({**dict(zip(tickers, weights)), "expected_return": expected, "volatility": volatility,
                     "worst_12_month_return": worst, "meets_mandate": all(rule["pass"] for rule in rules)})
    return pd.DataFrame(rows)
