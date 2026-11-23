"""Investor-specific rules used by the Compass portfolio engine."""
from __future__ import annotations
from dataclasses import dataclass

FUNDS = ("SGOV", "IEF", "USIG", "VT")
BENCHMARK_WEIGHTS = (0.00, 0.40, 0.00, 0.60)
PORTFOLIO_SIZE_DOLLARS = 100_000_000
QUARTERLY_PAYOUT_DOLLARS = 750_000
MINIMUM_RESERVE_WEIGHT = 4 * QUARTERLY_PAYOUT_DOLLARS / PORTFOLIO_SIZE_DOLLARS
MAXIMUM_FUND_WEIGHT = .60
USE_MAXIMUM_FUND_WEIGHT = True
OBJECTIVE_SPREAD_OVER_INFLATION = .04
HORIZON_YEARS = 7
GRID_STEP = .05
TOLERANCE = 1e-9

@dataclass(frozen=True)
class Mandate:
    name: str
    portfolio_size_dollars: float
    objective_kind: str = "inflation plus a spread"
    objective_spread: float = .04
    required_real_return: float | None = None
    horizon_years: int = 7
    minimum_reserve_weight: float = .03
    reserve_funds: tuple[str, ...] = ("SGOV", "IEF")
    maximum_fund_weight: float | None = .60
    worst_12_month_drop_limit: float | None = None
    cash_flow_amount: float = 750_000
    cash_flow_frequency: str = "quarterly payout"
    benchmark_weights: tuple[float, ...] = BENCHMARK_WEIGHTS
    max_single_stock_weight: float | None = None
    max_individual_stocks_total: float | None = None
    min_holdings: int | None = None

    def objective(self, inflation: float) -> float:
        real = self.required_real_return if self.objective_kind == "fixed required real return plus inflation" else self.objective_spread
        return inflation + (real or 0.0)

    def check(self, weights, estimates, inflation, funds=None):
        """Return a plain-language result for every applicable investment rule."""
        expected = estimates if isinstance(estimates, (int, float)) else estimates.get("expected_return", 0.0)
        tickers = tuple(f.ticker for f in funds) if funds is not None else FUNDS
        values = tuple(weights[ticker] for ticker in tickers) if isinstance(weights, dict) else tuple(weights)
        rules = [
            {"rule": "Long-only", "pass": all(w >= -TOLERANCE for w in values), "measured_value": min(values), "limit": 0.0},
            {"rule": "Weights sum to 100%", "pass": abs(sum(values)-1) <= TOLERANCE, "measured_value": sum(values), "limit": 1.0},
        ]
        reserve = sum(values[tickers.index(f)] for f in self.reserve_funds if f in tickers)
        rules.append({"rule": "Emergency reserve" if self.name != "Meridian Foundation" else "At least 3% in SGOV + IEF",
                      "pass": reserve >= self.minimum_reserve_weight-TOLERANCE, "measured_value": reserve, "limit": self.minimum_reserve_weight})
        if self.maximum_fund_weight is not None:
            rules.append({"rule": f"No fund above {self.maximum_fund_weight:.0%}", "pass": max(values) <= self.maximum_fund_weight+TOLERANCE,
                          "measured_value": max(values), "limit": self.maximum_fund_weight})
        rules.append({"rule": "Return at least inflation plus required return", "pass": expected >= self.objective(inflation)-TOLERANCE,
                      "measured_value": expected, "limit": self.objective(inflation)})
        if self.worst_12_month_drop_limit is not None and isinstance(estimates, dict) and "monthly_returns" in estimates:
            import numpy as np
            monthly_values = estimates["monthly_returns"].to_numpy() @ np.asarray(values)
            worst = min(np.prod(1 + monthly_values[i:i+12])-1 for i in range(max(1, len(monthly_values)-11)))
            rules.append({"rule": "Largest 12-month drop", "pass": worst >= -self.worst_12_month_drop_limit-TOLERANCE,
                          "measured_value": float(worst), "limit": -self.worst_12_month_drop_limit})
        if funds is not None:
            stock_values = [value for value, fund in zip(values, funds) if fund.role == "individual stock"]
            if self.max_single_stock_weight is not None:
                largest_stock = max(stock_values, default=0.0)
                rules.append({"rule": "No individual stock above the diversification limit",
                              "pass": largest_stock <= self.max_single_stock_weight + TOLERANCE,
                              "measured_value": largest_stock, "limit": self.max_single_stock_weight})
            if self.max_individual_stocks_total is not None:
                total_stocks = sum(stock_values)
                rules.append({"rule": "Individual stocks combined stay within the diversification limit",
                              "pass": total_stocks <= self.max_individual_stocks_total + TOLERANCE,
                              "measured_value": total_stocks, "limit": self.max_individual_stocks_total})
            if self.min_holdings is not None:
                holding_count = sum(value >= .02 - TOLERANCE for value in values)
                rules.append({"rule": "At least the minimum number of holdings are at least 2%",
                              "pass": holding_count >= self.min_holdings,
                              "measured_value": holding_count, "limit": self.min_holdings})
        return rules

MERIDIAN = Mandate("Meridian Foundation", PORTFOLIO_SIZE_DOLLARS, horizon_years=HORIZON_YEARS,
                   minimum_reserve_weight=MINIMUM_RESERVE_WEIGHT, cash_flow_amount=QUARTERLY_PAYOUT_DOLLARS)

def check_portfolio(weights, expected_return, inflation, *, reserve_minimum=MINIMUM_RESERVE_WEIGHT,
                    use_maximum_fund_weight=USE_MAXIMUM_FUND_WEIGHT, maximum_fund_weight=MAXIMUM_FUND_WEIGHT,
                    objective_spread=OBJECTIVE_SPREAD_OVER_INFLATION):
    mandate = Mandate("Meridian Foundation", PORTFOLIO_SIZE_DOLLARS, objective_spread=objective_spread,
                      minimum_reserve_weight=reserve_minimum, maximum_fund_weight=maximum_fund_weight if use_maximum_fund_weight else None)
    rules = mandate.check(weights, expected_return, inflation)
    rules[2]["rule"] = f"At least {reserve_minimum:.0%} in SGOV + IEF"
    if not use_maximum_fund_weight:
        rules.insert(3, {"rule": "No fund above 60% (turned off)", "pass": True})
    rules[-1]["rule"] = "Return at least inflation + objective spread"
    return rules

def passes_mandate(*args, **kwargs): return all(rule["pass"] for rule in check_portfolio(*args, **kwargs))
