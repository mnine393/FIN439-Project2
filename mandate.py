"""The editable investment mandate and its rule-by-rule checks."""
from __future__ import annotations

# EDITABLE CONSTANTS ---------------------------------------------------------
FUNDS = ("SGOV", "IEF", "USIG", "VT")
BENCHMARK_WEIGHTS = (0.00, 0.40, 0.00, 0.60)
PORTFOLIO_SIZE_DOLLARS = 100_000_000
QUARTERLY_PAYOUT_DOLLARS = 750_000
# The 3% reserve rule equals four quarterly payouts divided by portfolio size.
MINIMUM_RESERVE_WEIGHT = 4 * QUARTERLY_PAYOUT_DOLLARS / PORTFOLIO_SIZE_DOLLARS
MAXIMUM_FUND_WEIGHT = 0.60
USE_MAXIMUM_FUND_WEIGHT = True
OBJECTIVE_SPREAD_OVER_INFLATION = 0.04
HORIZON_YEARS = 7
GRID_STEP = 0.05
TOLERANCE = 1e-9


def check_portfolio(weights, expected_return, inflation, *, reserve_minimum=MINIMUM_RESERVE_WEIGHT,
                    use_maximum_fund_weight=USE_MAXIMUM_FUND_WEIGHT,
                    maximum_fund_weight=MAXIMUM_FUND_WEIGHT,
                    objective_spread=OBJECTIVE_SPREAD_OVER_INFLATION):
    """Return each mandate rule and its pass or fail result for a portfolio."""
    if len(weights) != len(FUNDS):
        raise ValueError("The portfolio must have one weight for each fund.")
    objective = None if inflation is None else inflation + objective_spread
    rules = [
        {"rule": "Long-only", "pass": all(weight >= -TOLERANCE for weight in weights)},
        {"rule": "Weights sum to 100%", "pass": abs(sum(weights) - 1) <= TOLERANCE},
        {"rule": f"At least {reserve_minimum:.0%} in SGOV + IEF",
         "pass": weights[0] + weights[1] >= reserve_minimum - TOLERANCE},
    ]
    if use_maximum_fund_weight:
        rules.append({"rule": f"No fund above {maximum_fund_weight:.0%}",
                      "pass": max(weights) <= maximum_fund_weight + TOLERANCE})
    else:
        rules.append({"rule": "No fund above 60% (turned off)", "pass": True})
    rules.append({"rule": "Return at least inflation + objective spread",
                  "pass": objective is not None and expected_return >= objective - TOLERANCE})
    return rules


def passes_mandate(*args, **kwargs):
    """Return whether a portfolio passes every stated rule."""
    return all(rule["pass"] for rule in check_portfolio(*args, **kwargs))
