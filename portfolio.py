"""Monthly-price estimates and a transparent four-fund long-only grid search."""
from __future__ import annotations

from math import sqrt
import pandas as pd


def estimate_from_monthly_prices(prices: pd.DataFrame, last_36_months: bool = False) -> dict:
    table = prices.copy()
    dates = pd.to_datetime(table.iloc[:, 0], errors="coerce")
    if dates.isna().any() or not dates.is_monotonic_increasing or dates.duplicated().any():
        raise ValueError("The first CSV column must be unique dates in oldest-first order.")
    values = table.iloc[:, 1:].apply(pd.to_numeric, errors="coerce")
    if values.isna().any().any() or (values <= 0).any().any():
        raise ValueError("Prices must be positive numbers without missing values.")
    returns = values.pct_change(fill_method=None).iloc[1:]
    if last_36_months:
        returns = returns.tail(36)
    if len(returns) < 2:
        raise ValueError("At least three monthly price rows are required.")
    return {"names": tuple(values.columns), "returns": tuple((returns.mean() * 12).tolist()),
            "volatilities": tuple((returns.std(ddof=1) * sqrt(12)).tolist()),
            "correlation": returns.corr().to_numpy(), "monthly_returns": returns}


def estimate_from_monthly_returns(returns: pd.DataFrame, window: str = "all history") -> dict:
    """Estimate annual figures from a return table, with an optional trailing window."""
    values = returns.loc[:, [column for column in returns.columns if column in ("SGOV", "IEF", "USIG", "VT")]].copy()
    values = values.apply(pd.to_numeric, errors="coerce")
    if values.isna().any().any() or len(values) < 2:
        raise ValueError("At least two complete monthly return rows are required.")
    months = {"all history": None, "last 60 months": 60, "last 36 months": 36}.get(window)
    if window not in ("all history", "last 60 months", "last 36 months"):
        raise ValueError("The estimate window must be all history, last 60 months, or last 36 months.")
    if months is not None:
        values = values.tail(months)
    return {"names": tuple(values.columns), "returns": tuple((values.mean() * 12).tolist()),
            "volatilities": tuple((values.std(ddof=1) * sqrt(12)).tolist()),
            "correlation": values.corr().to_numpy(), "monthly_returns": values}


def portfolio_metrics(weights, estimates: dict) -> tuple[float, float]:
    returns = estimates["returns"]
    volatility = estimates["volatilities"]
    correlation = estimates["correlation"]
    expected = sum(weight * value for weight, value in zip(weights, returns))
    variance = sum(weights[i] * correlation[i][j] * volatility[i] * volatility[j] * weights[j]
                   for i in range(len(weights)) for j in range(len(weights)))
    return expected, sqrt(max(variance, 0))


def search_lowest_volatility(estimates: dict, checker, step: float = 0.05):
    """Test every five-point long-only mix and return the feasible least volatile one."""
    units = round(1 / step)
    best = None
    for a in range(units + 1):
        for b in range(units - a + 1):
            for c in range(units - a - b + 1):
                weights = (a * step, b * step, c * step, (units - a - b - c) * step)
                expected, volatility = portfolio_metrics(weights, estimates)
                rules = checker(weights, expected)
                if all(rule["pass"] for rule in rules):
                    candidate = {"weights": weights, "expected_return": expected,
                                 "volatility": volatility, "rules": rules}
                    if best is None or volatility < best["volatility"] - 1e-12:
                        best = candidate
    return best
