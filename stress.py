"""Required stress cases for the constrained investment portfolio."""
from __future__ import annotations

from mandate import BENCHMARK_WEIGHTS, FUNDS, GRID_STEP, PORTFOLIO_SIZE_DOLLARS, check_portfolio
from portfolio import estimate_from_monthly_prices, estimate_from_monthly_returns, search_lowest_volatility

RETURN_SHIFTS = (-0.01, 0.01)
TRANSACTION_COSTS_BASIS_POINTS = (0, 10, 25, 50)
RESERVE_MINIMUMS = (0.10, 0.20)


def constrained_mix(estimates, inflation, reserve_minimum, cap_on, objective_spread):
    return search_lowest_volatility(
        estimates,
        lambda w, r: check_portfolio(w, r, inflation, reserve_minimum=reserve_minimum,
                                     use_maximum_fund_weight=cap_on, objective_spread=objective_spread), GRID_STEP)


def run_stress(prices, inflation, base_weights, objective_spread=None, mandate=None):
    """Return all required independent stress cases; costs reduce first-year return only."""
    if mandate is not None:
        objective_spread = mandate.objective_spread
    if objective_spread is None:
        objective_spread = .04
    rows = []
    is_returns = "month" in prices.columns
    estimator = (lambda window="all history": estimate_from_monthly_returns(prices, window)) if is_returns else None
    base_estimates = estimator() if is_returns else estimate_from_monthly_prices(prices)
    for fund_index, fund in enumerate(FUNDS):
        for shift in RETURN_SHIFTS:
            changed = dict(base_estimates)
            returns = list(base_estimates["returns"])
            returns[fund_index] += shift
            changed["returns"] = tuple(returns)
            direction = "lower" if shift < 0 else "higher"
            rows.append(_row(f"{fund} expected return one point {direction}", "Estimates", changed,
                             inflation, .03, True, objective_spread, base_weights, None))
    for months in (60, 36):
        estimates = estimator(f"last {months} months") if is_returns else estimate_from_monthly_prices(prices, months == 36)
        rows.append(_row(f"Estimate window: last {months} months", "Data window", estimates, inflation,
                         .03, True, objective_spread, base_weights, None))
    for cost in TRANSACTION_COSTS_BASIS_POINTS:
        rows.append(_row(f"Trading cost {cost} basis points", "Costs", base_estimates, inflation, .03, True,
                         objective_spread, base_weights, cost / 10000))
    for minimum in RESERVE_MINIMUMS:
        rows.append(_row(f"Reserve minimum {minimum:.0%}", "Rules", base_estimates, inflation, minimum, True,
                         objective_spread, base_weights, None))
    rows.append(_row("60% fund cap removed", "Rules", base_estimates, inflation, .03, False,
                     objective_spread, base_weights, None))
    return rows


def _row(case, group, estimates, inflation, minimum, cap_on, spread, base_weights, transaction_cost):
    mix = constrained_mix(estimates, inflation, minimum, cap_on, spread)
    if mix is None:
        return {"case": case, "group": group, "weights": None, "meets_objective": False, "largest_weight_change": None,
                "turnover": None, "expected_return_after_cost": None, "trading_cost_dollars": None}
    expected = mix["expected_return"]
    turnover = None
    trading_cost_dollars = None
    if transaction_cost is not None:
        turnover = sum(abs(a - b) for a, b in zip(mix["weights"], BENCHMARK_WEIGHTS)) / 2
        expected -= turnover * transaction_cost
        trading_cost_dollars = turnover * transaction_cost * PORTFOLIO_SIZE_DOLLARS
    change = None if base_weights is None else max(abs(a - b) for a, b in zip(mix["weights"], base_weights))
    return {"case": case, "group": group, "weights": mix["weights"], "meets_objective": expected >= inflation + spread,
            "largest_weight_change": change,
            "turnover": turnover, "expected_return_after_cost": expected,
            "trading_cost_dollars": trading_cost_dollars}
