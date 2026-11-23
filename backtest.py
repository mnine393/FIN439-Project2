"""Expanding-window, point-in-time endowment backtest."""
from __future__ import annotations

from math import sqrt
import numpy as np
import pandas as pd

from cpi_signal import load_cpi_vintages
from mandate import (BENCHMARK_WEIGHTS, FUNDS, GRID_STEP, OBJECTIVE_SPREAD_OVER_INFLATION,
                     PORTFOLIO_SIZE_DOLLARS, QUARTERLY_PAYOUT_DOLLARS, check_portfolio)
from portfolio import estimate_from_monthly_returns, search_lowest_volatility


def _hard_limit_mix(estimates, inflation):
    """Highest-return mix that satisfies constraints other than the objective."""
    return search_lowest_volatility(estimates, lambda w, r: [rule for rule in check_portfolio(w, r, inflation)
                                                               if not rule["rule"].startswith("Return at least")], GRID_STEP)


def _choose_mix(history: pd.DataFrame, inflation: float):
    estimates = estimate_from_monthly_returns(history)
    candidate = search_lowest_volatility(estimates, lambda w, r: check_portfolio(w, r, inflation), GRID_STEP)
    if candidate is not None:
        return candidate["weights"], False
    # search_lowest_volatility selects lowest risk; this explicit grid search selects highest return.
    best = None
    from frontier import all_long_only_mixes
    from portfolio import portfolio_metrics
    for weights in all_long_only_mixes():
        expected, _ = portfolio_metrics(weights, estimates)
        hard_rules = [rule for rule in check_portfolio(weights, expected, inflation)
                      if not rule["rule"].startswith("Return at least")]
        if all(rule["pass"] for rule in hard_rules) and (best is None or expected > best[0]):
            best = (expected, weights)
    return best[1] if best else None, True


def _metrics(history: list[dict]) -> dict:
    frame = pd.DataFrame(history)
    returns = frame["net_return"].to_numpy()
    years = len(returns) / 12
    annualized = float(np.prod(1 + returns) ** (1 / years) - 1)
    volatility = float(np.std(returns, ddof=1) * sqrt(12))
    values = frame["value"].to_numpy()
    drawdown = values / np.maximum.accumulate(values) - 1
    return {"annualized_return": annualized, "volatility": volatility, "worst_peak_to_trough_drop": float(drawdown.min()),
            "ending_dollar_value": float(values[-1]), "objective_not_reachable_months": int(frame["objective_not_reachable"].sum()),
            "average_turnover": float(frame["turnover"].mean())}


def run_backtest(monthly_returns: pd.DataFrame, *, trading_cost_basis_points: float = 10,
                 cpi_vintages: pd.DataFrame | None = None, mandate=None) -> dict:
    """Backtest constrained, equal-weight, and benchmark portfolios without future return use."""
    returns = monthly_returns.loc[:, list(FUNDS)].reset_index(drop=True)
    months = pd.to_datetime(monthly_returns["month"]).reset_index(drop=True)
    decision_indexes = list(range(35, len(returns) - 1))
    decision_dates = [(months.iloc[index] + pd.offsets.MonthEnd(0)).date() for index in decision_indexes]
    if cpi_vintages is None:
        cpi_vintages, _ = load_cpi_vintages(decision_dates)
    inflation_by_date = dict(zip(pd.to_datetime(cpi_vintages["decision_date"]).dt.date, cpi_vintages["inflation"]))
    strategies = {"Constrained portfolio": [], "Equal weight": [], "60/40 benchmark": []}
    # These are the weights actually held after the previous month's returns.
    # Comparing a new target with these drifted weights applies the same
    # rebalance accounting to every strategy.
    drifted = {name: None for name in strategies}
    values = {name: PORTFOLIO_SIZE_DOLLARS for name in strategies}
    cost_rate = trading_cost_basis_points / 10_000
    for index, decision_date in zip(decision_indexes, decision_dates):
        inflation = float(inflation_by_date[decision_date])
        chosen, unreachable = _choose_mix(returns.iloc[:index + 1], inflation)
        current = {"Constrained portfolio": chosen, "Equal weight": (.25, .25, .25, .25),
                   "60/40 benchmark": BENCHMARK_WEIGHTS}
        for name, weights in current.items():
            if weights is None:
                continue
            turnover = 0.0 if drifted[name] is None else sum(abs(a - b) for a, b in zip(weights, drifted[name])) / 2
            asset_returns = returns.iloc[index + 1].to_numpy()
            gross = float(np.dot(asset_returns, weights))
            net = gross - turnover * cost_rate
            values[name] *= 1 + net
            held_month = months.iloc[index + 1]
            if held_month.month in (3, 6, 9, 12):
                values[name] -= QUARTERLY_PAYOUT_DOLLARS
            strategies[name].append({"month": held_month, "value": values[name], "net_return": net,
                                     "turnover": turnover, "objective_not_reachable": unreachable if name == "Constrained portfolio" else False,
                                     **dict(zip(FUNDS, weights))})
            # Values grow at asset-specific rates before the next decision.
            drifted[name] = tuple(np.asarray(weights) * (1 + asset_returns) / (1 + gross))
    return {"histories": {name: pd.DataFrame(rows) for name, rows in strategies.items()},
            "summary": pd.DataFrame([{"portfolio": name, **_metrics(rows)} for name, rows in strategies.items()])}
