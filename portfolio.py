"""Monthly-price estimates and a transparent four-fund long-only grid search."""
from __future__ import annotations

from math import sqrt
import pandas as pd
import numpy as np
from scipy.optimize import minimize


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


def estimate_from_monthly_returns(returns: pd.DataFrame, window: str = "all history", tickers=None) -> dict:
    """Estimate annual figures from a return table, with an optional trailing window."""
    selected = list(tickers) if tickers is not None else [column for column in returns.columns if column in ("SGOV", "IEF", "USIG", "VT")]
    values = returns.loc[:, selected].copy()
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


def search_lowest_volatility(estimates: dict, checker=None, step: float = 0.05, *, mandate=None, inflation=None):
    """Test every five-point long-only mix and return the feasible least volatile one."""
    if checker is None:
        if mandate is None or inflation is None:
            raise ValueError("Provide a rule checker or a mandate and inflation rate.")
        checker = lambda weights, expected: mandate.check(weights, {"expected_return": expected, "monthly_returns": estimates.get("monthly_returns")}, inflation)
    units = round(1 / step)
    best = None
    from mixes import mix_matrix
    for weights in mix_matrix(len(estimates["returns"]), step):
        weights = tuple(weights)
        expected, volatility = portfolio_metrics(weights, estimates)
        rules = checker(weights, expected)
        if all(rule["pass"] for rule in rules):
            candidate = {"weights": weights, "expected_return": expected,
                         "volatility": volatility, "rules": rules}
            if best is None or volatility < best["volatility"] - 1e-12:
                best = candidate
    return best


def rounded_weights(weights) -> tuple[float, ...]:
    """Round long-only weights to whole percentages while retaining a 100% total."""
    values = np.asarray(weights, dtype=float)
    cents = np.floor(values * 100 + 1e-9).astype(int)
    remaining = 100 - int(cents.sum())
    fractions = values * 100 - cents
    for index in np.argsort(-fractions)[:remaining]:
        cents[index] += 1
    return tuple(cents / 100)


def optimize_lowest_volatility(estimates: dict, checker, mandate, inflation: float, funds,
                               objective: float | None = None) -> dict | None:
    """Solve a long-only constrained allocation, then accept only an exactly checked rounded mix."""
    values = estimates["monthly_returns"].to_numpy(float)
    means = values.mean(axis=0) * 12
    covariance = np.cov(values, rowvar=False, ddof=1) * 12
    count = len(funds)
    target = mandate.objective(inflation) if objective is None else objective
    reserve_indexes = [index for index, fund in enumerate(funds) if fund.ticker in mandate.reserve_funds]
    stock_indexes = [index for index, fund in enumerate(funds) if fund.role == "individual stock"]
    cap = 1.0 if mandate.maximum_fund_weight is None else mandate.maximum_fund_weight
    bounds = []
    for fund in funds:
        upper = cap
        if fund.role == "individual stock" and mandate.max_single_stock_weight is not None:
            upper = min(upper, mandate.max_single_stock_weight)
        bounds.append((0.0, upper))

    def variance(weights):
        return float(weights @ covariance @ weights)

    def variance_gradient(weights):
        return 2 * covariance @ weights

    def selector(indexes):
        """A 0/1 row that adds up the weights of the chosen holdings."""
        row = np.zeros(count)
        row[indexes] = 1.0
        return row

    reserve_row = selector(reserve_indexes)
    stock_row = selector(stock_indexes)
    constraints = [
        {"type": "eq", "fun": lambda weights: weights.sum() - 1, "jac": lambda weights: np.ones(count)},
        {"type": "ineq", "fun": lambda weights: float(weights @ means - target), "jac": lambda weights: means},
        {"type": "ineq", "fun": lambda weights: float(weights @ reserve_row - mandate.minimum_reserve_weight),
         "jac": lambda weights: reserve_row},
    ]
    if mandate.max_individual_stocks_total is not None:
        constraints.append({"type": "ineq", "fun": lambda weights: float(
            mandate.max_individual_stocks_total - weights @ stock_row), "jac": lambda weights: -stock_row})
    if mandate.worst_12_month_drop_limit is not None:
        # One linear rule per rolling 12-month window: the window's summed monthly returns must be at least
        # log(1 - tolerated drop). Each window's sum is a fixed row times the weights, so the rows are built once.
        # The exact compounded worst 12-month return is still checked by `checker` after rounding.
        window_rows = np.array([values[index:index + 12].sum(axis=0)
                                for index in range(max(1, len(values) - 11))])
        floor = np.log(1 - mandate.worst_12_month_drop_limit)
        constraints.append({"type": "ineq", "fun": lambda weights: window_rows @ weights - floor,
                            "jac": lambda weights: window_rows})
    starts = [np.repeat(1 / count, count)]
    for index in range(count):
        start = np.zeros(count)
        start[index] = min(cap, 1.0)
        if start.sum() < 1 and reserve_indexes:
            start[reserve_indexes[0]] += 1 - start.sum()
        if abs(start.sum() - 1) < 1e-9 and np.all(start <= cap + 1e-9):
            starts.append(start)
    best = None
    # The optimum usually sits exactly on a limit, so rounding to whole percents can push it just over.
    # When no rounded answer passes the exact checks, ask for a little more margin and solve again.
    for attempt in range(20):
        margin = 0.0005 * attempt
        tightened = list(constraints)
        tightened[1] = {"type": "ineq", "fun": lambda weights, extra=margin: float(weights @ means - target - extra),
                        "jac": lambda weights: means}
        for start in starts:
            result = minimize(variance, start, jac=variance_gradient, method="SLSQP", bounds=bounds,
                              constraints=tightened, options={"maxiter": 500, "ftol": 1e-10})
            if not result.success:
                continue
            weights = rounded_weights(result.x)
            expected, volatility = portfolio_metrics(weights, estimates)
            rules = checker(weights, expected)
            if all(rule["pass"] for rule in rules):
                candidate = {"weights": weights, "expected_return": expected, "volatility": volatility,
                             "rules": rules, "method": "optimizer"}
                if best is None or candidate["volatility"] < best["volatility"]:
                    best = candidate
        if best is not None:
            return best
    return best


def search_portfolio(estimates: dict, checker, mandate, inflation: float, funds, step: float = .05):
    """Use the documented grid for eight or fewer holdings and the optimizer above that."""
    holding_count = len(estimates["returns"])
    if holding_count != len(funds):
        raise ValueError("Portfolio estimates and the investment universe must contain the same holdings.")
    if holding_count <= 8:
        result = search_lowest_volatility(estimates, checker, step)
        if result is not None:
            result["method"] = f"grid, {int(step * 100)}-point steps"
        return result
    return optimize_lowest_volatility(estimates, checker, mandate, inflation, funds)
