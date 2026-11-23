"""Compass JSON service."""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from functools import lru_cache
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backtest import run_backtest
from cpi_signal import DEFAULT_DECISION_DATE, cpi_signal, load_cpi_as_known, load_first_publication_date
from data import (load_crisis_reference_returns, load_monthly_returns, load_fund_prices,
                  load_universe_returns)
from frontier import evaluate_frontier
from mandate import BENCHMARK_WEIGHTS, FUNDS, Mandate
from mixes import mix_statistic
from personal import (PersonalInputs, choose_personal_mix, contribution_for_80_percent,
                      emergency_reserve, personal_backtest, personal_simulation, plan,
                      required_real_return)
from portfolio import estimate_from_monthly_returns, portfolio_metrics, search_lowest_volatility, search_portfolio
from simulation import fan_chart_frame, simulate_portfolio
from forecast import forecast_portfolio, calibration_test
from analyze import analyze_portfolio, compare_portfolios, risk_profile, QUESTIONS
from stress import run_stress
import recommendation
from committee import committee_report
from universe import DEFAULT_UNIVERSE, Fund, benchmark_weights, guessed_role, is_default, make_funds, normalize_ticker
import legends
import screens

AI_STATEMENT = ("AI use: OpenAI Codex (GPT-5.6-Terra) built the analysis engine; Claude built the website and helped "
                "plan and check; the analysis and the decision are mine.")
ADVICE_STATEMENT = "Education, not investment advice."
app = FastAPI(title="Compass")
LEGEND_KEYS = {
    "buffett": {"cik": "0001067983", "person": "Warren Buffett"},
    "burry": {"cik": "0001649339", "person": "Michael Burry"},
}
SUGGESTED_MAX_SINGLE_STOCK_WEIGHT = .10
SUGGESTED_MAX_INDIVIDUAL_STOCKS_TOTAL = .50
SUGGESTED_MIN_HOLDINGS = 5


class PersonalRequest(BaseModel):
    """Validate personal planning input before costly planning begins."""
    savings: float = Field(ge=0)
    monthly_contribution: float = Field(ge=0)
    goal: float = Field(gt=0)
    years: int = Field(gt=0, le=60)
    tolerated_drop: float = Field(ge=0, le=1)
    monthly_expenses: float = Field(ge=0)
    reserve_months: int = Field(ge=0, le=120)
    holdings: dict[str, float] | None = None
    other_cash: float = Field(default=0, ge=0)
    trading_cost_basis_points: float = Field(default=10, ge=0, le=1000)
    seed: int = 439
    universe: list[dict] | None = None
    max_single_stock_weight: float | None = Field(default=None, ge=0, le=1)
    max_individual_stocks_total: float | None = Field(default=None, ge=0, le=1)
    min_holdings: int | None = Field(default=None, ge=1, le=15)


class CommitteeLiveRequest(BaseModel):
    """Validate a request for fresh optional committee memos."""
    mode: str
    inputs: dict | None = None
    settings: dict | None = None


class PortfolioAnalysisRequest(BaseModel):
    """Validate the additive portfolio-analysis application programming interface."""
    holdings: dict[str, float]
    roles: dict[str, str] | None = None
    horizon_years: int = Field(default=10, ge=1, le=40)
    monthly_flow: float = 0.0


class PortfolioCompareRequest(BaseModel):
    a: dict[str, float]
    b: dict[str, float]
    roles: dict[str, str] | None = None
    horizon_years: int = Field(default=10, ge=1, le=40)


class CalibrationRequest(BaseModel):
    """Validate walk-forward calibration inputs before loading market history."""
    holdings: dict[str, float] | None = None
    tickers: list[str] | None = None
    weights: list[float] | None = None
    roles: dict[str, str] | None = None


class RiskProfileRequest(BaseModel):
    answers: dict[str, int]


def clean(value, key: str | None = None):
    """Recursively turn scientific and tabular values into JSON-safe built-in values."""
    if isinstance(value, np.ndarray):
        return [clean(item, key) for item in value.tolist()]
    if isinstance(value, np.generic):
        return clean(value.item(), key)
    if isinstance(value, pd.DataFrame):
        return clean(value.to_dict("records"), key)
    if isinstance(value, pd.Series):
        return clean(value.to_dict(), key)
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        if key == "weights" or key in FUNDS:
            return round(value, 2)
        money_names = {
            "value", "p10", "p25", "p50", "p75", "p90", "ending_value", "total_contributed",
            "reserve_target", "amount_set_aside_now", "shortfall", "invested_starting_amount",
            "savings", "monthly_contribution", "goal", "monthly_expenses", "other_cash",
            "cash_flow_amount",
        }
        if key and ("dollar" in key or key in money_names):
            return round(value, 2)
        return value
    if isinstance(value, (tuple, list)):
        return [clean(item, key) for item in value]
    if isinstance(value, dict):
        return {str(item_key): clean(item, str(item_key)) for item_key, item in value.items()}
    return value


def envelope(payload: dict) -> dict:
    """Attach required statements after all values have been made JSON-safe."""
    result = clean(payload)
    result["statements"] = [AI_STATEMENT, ADVICE_STATEMENT]
    return result


def weight_object(weights, tickers=FUNDS) -> dict | None:
    """Present a weight vector as a ticker-keyed object."""
    return None if weights is None else dict(zip(tickers, weights))


def diversification_summary(weights, funds: tuple[Fund, ...]) -> dict | None:
    """Summarize concentration using the same whole-portfolio weights shown to users."""
    if weights is None:
        return None
    values = np.asarray(weights, dtype=float)
    stock_total = sum(value for value, fund in zip(values, funds) if fund.role == "individual stock")
    return {"holdings_above_2_percent": int(np.sum(values >= .02)), "largest_weight": float(values.max()),
            "individual_stocks_total": float(stock_total),
            "effective_number_of_holdings": float(1 / np.sum(values ** 2))}


def rounded_frontier(frame: pd.DataFrame | list[dict], tickers=FUNDS) -> list[dict]:
    """Round frontier numeric values to keep response sizes practical."""
    records = frame.to_dict("records") if isinstance(frame, pd.DataFrame) else frame
    results = []
    for source in records:
        row = dict(source)
        weights = row.pop("weights", None)
        if weights is None and all(fund in row for fund in tickers):
            weights = tuple(row.pop(fund) for fund in tickers)
        result = {key: round(value, 5) if isinstance(value, (float, np.floating)) else value
                  for key, value in row.items()}
        result["weights"] = weight_object(weights, tickers)
        results.append(result)
    return results


def normalize_weight_rows(rows: list[dict], tickers=FUNDS) -> list[dict]:
    """Copy response rows and replace every mix vector with ticker-keyed weights."""
    normalized = []
    for source in rows:
        row = dict(source)
        row["weights"] = weight_object(row.get("weights"), tickers)
        normalized.append(row)
    return normalized


def stop_summary(rows: list[dict], base_weights, threshold: float) -> dict:
    """Summarize mix changes using the stated stop rule."""
    if base_weights is None:
        return {"triggered": True, "threshold": threshold, "triggered_case_count": 0,
                "triggered_cases": [], "largest_weight_change": None,
                "largest_weight_change_case": None, "no_mix_case_count": 0,
                "reason": "no mix meets the mandate in the base case"}
    triggered_cases = []
    largest_change = None
    largest_case = None
    no_mix_case_count = 0
    for row in rows:
        weights = row.get("weights")
        change = None if weights is None else max(
            abs(weight - base) for weight, base in zip(weights, base_weights)
        )
        row["largest_weight_change"] = change
        if change is None:
            no_mix_case_count += 1
        elif change > 0 and (largest_change is None or change > largest_change):
            largest_change = change
            largest_case = row["case"]
        if weights is None or (change is not None and change > threshold):
            triggered_cases.append(row["case"])
    if no_mix_case_count:
        reason = f"{no_mix_case_count} stress cases leave no mix meeting the mandate"
    else:
        reason = (f"{len(triggered_cases)} stress cases move a weight by more than {threshold:.0%} points"
                  if triggered_cases else "stable")
    return {"triggered": bool(triggered_cases), "threshold": threshold,
            "triggered_case_count": len(triggered_cases), "triggered_cases": triggered_cases,
            "largest_weight_change": largest_change, "largest_weight_change_case": largest_case,
            "no_mix_case_count": no_mix_case_count, "reason": reason}


def institution_mandate_rules(mandate: Mandate) -> list[str]:
    """Explain every Meridian Foundation rule in language suitable for the website."""
    fund_lines = {"SGOV": "SGOV: short United States Treasury bill fund.",
                  "IEF": "IEF: intermediate United States Treasury bond fund.",
                  "USIG": "USIG: investment-grade corporate bond fund.",
                  "VT": "VT: global stock fund."}
    return [
        f"Objective: earn inflation plus {mandate.objective_spread:.0%} a year.",
        "Investment universe:", *fund_lines.values(),
        "Benchmark: 60% VT and 40% IEF.",
        "Risk measure: the worst rolling 12-month return and annualized volatility.",
        "Limit: investments are long-only and weights must total 100%.",
        f"Limit: at least {mandate.minimum_reserve_weight:.0%} must be in SGOV and IEF.",
        f"Limit: no fund may exceed {mandate.maximum_fund_weight:.0%} when the fund cap is on.",
        f"Portfolio size: ${mandate.portfolio_size_dollars:,.0f}.",
        f"Quarterly payout: ${mandate.cash_flow_amount:,.0f}.",
        "The reserve rule is 3% because four quarterly payouts equal 3% of the portfolio.",
    ]


def locked_record() -> dict:
    """Expose the locked prediction materials without changing their source records."""
    validation = Path("docs/validation-and-ai-use.md").read_text(encoding="utf-8")
    output = Path("output/locked_run_output.txt").read_text(encoding="utf-8")
    prediction = validation.split("**My prediction, written by me without AI, exactly as written:**", 1)[1]
    prediction = prediction.split("**Expected direction:**", 1)[0].strip()
    return {"prediction": prediction, "lock_date": "2026-11-12 15:48 Eastern",
            "old_value": "9.88% a year", "new_value": "7.88% a year",
            "result_lines": output.splitlines(), "validation_raw_text": validation,
            "locked_run_raw_text": output}


def universe_details(funds: tuple[Fund, ...], refresh: bool = False) -> list[dict]:
    """Read metadata for a universe without changing the default return source."""
    records = []
    for fund in funds:
        _, metadata = load_fund_prices(fund, refresh)
        records.append({"ticker": fund.ticker, "name": metadata.get("name") or fund.name or fund.ticker,
                        "role": fund.role, "reserve_eligible": fund.reserve_eligible,
                        "first_month": metadata.get("first_month"), "last_month": metadata.get("last_month"),
                        "downloaded_at": metadata.get("downloaded_at"),
                        "instrument_type": metadata.get("instrument_type")})
    return records


def universe_payload(funds: tuple[Fund, ...], records: list[dict], returns: pd.DataFrame, step: float,
                     mandate: Mandate | None = None, method: str | None = None) -> dict:
    """Describe the data window and grid used in an API response."""
    months = pd.to_datetime(returns["month"])
    window = {"first_month": months.iloc[0].date().isoformat(),
              "last_month": months.iloc[-1].date().isoformat(), "months": len(months)}
    if not is_default(funds):
        window["proxy_extended_tickers"] = {
            record["ticker"]: record["proxy_extension_start"]
            for record in records if record.get("proxy_extension_start") is not None
        }
    search_method = "optimizer" if len(funds) > 8 else f"grid, {int(step * 100)}-point steps"
    public_records = [{key: value for key, value in record.items() if key != "proxy_extension_start"}
                      for record in records]
    return {"funds": public_records, "window": window,
            "grid_step": step, "is_default": is_default(funds), "method": method or search_method,
            "diversification_rules": {
                "max_single_stock_weight": None if mandate is None else mandate.max_single_stock_weight,
                "max_individual_stocks_total": None if mandate is None else mandate.max_individual_stocks_total,
                "min_holdings": None if mandate is None else mandate.min_holdings,
            }}


def _legend(key: str) -> dict:
    """Return one supported legend or a readable not-found response."""
    try:
        return LEGEND_KEYS[key.lower()]
    except KeyError as error:
        raise HTTPException(404, "Legend must be buffett or burry.") from error


def _legend_summary(key: str, as_of: str) -> dict:
    """Present one 13F summary without exposing parser-only fields."""
    identity = _legend(key)
    summary = legends.legend_summary(identity["cik"], as_of)
    return {"filer": summary["filer"], "person": identity["person"],
            "report_period": summary["report_period"], "filing_date": summary["filing_date"],
            "days_to_file": summary["days_to_file"],
            "number_of_stock_holdings": summary["number_of_stock_holdings"],
            "top_5_weight": summary["top_5_weight"], "top_10_weight": summary["top_10_weight"],
            "largest_holding": _holding_payload(summary["largest_holding"]), "stale": summary["stale"],
            "stale_message": summary["stale_message"]}


def _holding_payload(row: dict | None) -> dict | None:
    """Use the documented holding field names while retaining useful disclosure identifiers."""
    if row is None:
        return None
    return {"issuer": row["issuer"], "class": row["title_of_class"], "ticker": row.get("ticker"),
            "value": row["value"], "shares": row["shares"], "weight": row.get("weight"),
            "cusip": row["cusip"], "put_call": row["put_call"]}


def _plain_measure(value) -> str:
    """Turn a screen measurement into a compact phrase for an API consumer."""
    if value is None:
        return "not known"
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, dict):
        return "; ".join(f"{name}: {_plain_measure(item)}" for name, item in value.items())
    if isinstance(value, (list, tuple)):
        return ", ".join(_plain_measure(item) for item in value)
    return str(value)


SCREEN_THRESHOLDS = {
    "roe_at_least_15_percent_every_year": "at least 15 percent every year",
    "owner_earnings_positive_every_year": "positive every year",
    "owner_earnings_grew_first_to_last": "the last year is greater than the first",
    "operating_cash_flow_at_least_net_income_every_year": "operating cash flow is at least net income every year",
    "liabilities_no_more_than_twice_equity_latest_year": "no more than two times equity in the latest year",
}


SCREEN_LABELS = {
    "roe_at_least_15_percent_every_year": "Return on equity of at least 15% every year",
    "owner_earnings_positive_every_year": "Owner earnings positive every year",
    "owner_earnings_grew_first_to_last": "Owner earnings grew, first year to last",
    "operating_cash_flow_at_least_net_income_every_year": "Cash from operations at least net income every year",
    "liabilities_no_more_than_twice_equity_latest_year": "Liabilities no more than twice equity, latest year",
}


def _screen_measure(name: str, value) -> str:
    """Format screen figures in the words used by the corresponding investor check."""
    if value is None:
        return "not known"
    if name.startswith("roe_"):
        if isinstance(value, list):
            # A missing year stays "not known"; it is never filled with an estimate.
            return ", ".join("not known" if item is None else f"{item:.2%}" for item in value)
        return f"{value:.2%}"
    if name.startswith("liabilities_"):
        return f"{value:.2f} times equity"
    if name.startswith("operating_cash_flow"):
        # Each year is a pair: operating cash flow, then net income.
        pairs = [f"cash {_billions(pair[0])} vs income {_billions(pair[1])}" for pair in value]
        return "; ".join(pairs)
    if name.startswith("owner_earnings_grew"):
        return f"first year {_billions(value.get('first'))}, last year {_billions(value.get('last'))}"
    if "owner_earnings" in name:
        return ", ".join(_billions(item) for item in value)
    return _plain_measure(value)


def _billions(value) -> str:
    """Write a dollar amount from a 10-K the way a person reads it: $93.0 billion, $512 million."""
    if value is None:
        return "not known"
    size = abs(value)
    sign = "-" if value < 0 else ""
    if size >= 1e9:
        return f"{sign}${size / 1e9:.1f} billion"
    if size >= 1e6:
        return f"{sign}${size / 1e6:.0f} million"
    return f"{sign}${size:,.0f}"


def _reduced_screen(result: dict) -> dict:
    """Return the small, plain-language screen record used by plan responses."""
    if result.get("status", "").startswith("not applicable"):
        return {"ticker": result["ticker"], "company_name": "not applicable",
                "buffett_score": "not applicable", "burry_score": "not applicable", "checks": [],
                "status": result["status"]}
    checks = []
    for investor in ("buffett", "burry"):
        for name, check in result.get(investor, {}).get("checks", {}).items():
            checks.append({"investor": investor, "check": SCREEN_LABELS.get(name, name.replace("_", " ")),
                           "result": check.get("status", "not known"),
                           "measured": _screen_measure(name, check.get("value")),
                           "threshold": SCREEN_THRESHOLDS.get(name, check.get("threshold", "not known"))})
    return {"ticker": result["ticker"], "company_name": result.get("company_name", "not found"),
            "buffett_score": result.get("buffett", {}).get("score", "not known").replace("Buffett ", ""),
            "burry_score": result.get("burry", {}).get("score", "not known").replace("Burry ", ""),
            "checks": checks}


@lru_cache(maxsize=256)
def _screen_cached(ticker: str, as_of: str) -> dict:
    """Cache a point-in-time stock screen shared by legends and custom plans."""
    return _reduced_screen(screens.screen_stock(ticker, as_of))


def _add_individual_stock_screens(payload: dict, funds: tuple[Fund, ...], as_of: str) -> None:
    """Attach stock screens only to custom universes that actually contain stocks."""
    tickers = [fund.ticker for fund in funds if fund.role == "individual stock"]
    if tickers:
        payload["screens"] = [_screen_cached(ticker, as_of) for ticker in tickers]


def _forecast_history(returns: pd.DataFrame, estimate_window: str) -> pd.DataFrame:
    """Keep the dated return rows that produced an estimate window."""
    months = {"all history": None, "last 60 months": 60, "last 36 months": 36}[estimate_window]
    return returns if months is None else returns.tail(months)


def custom_institution(funds: tuple[Fund, ...], cap_on: bool, reserve_minimum: float,
                       objective_spread: float, estimate_window: str, stop_threshold: float,
                       simulation_method: str, seed: int, max_single_stock_weight: float | None = None,
                       max_individual_stocks_total: float | None = None, min_holdings: int | None = None) -> dict:
    """Run the institutional engine for a non-default, role-described universe."""
    returns, records = load_universe_returns(funds, decision_date=DEFAULT_DECISION_DATE)
    funds = tuple(Fund(fund.ticker, fund.name,
                       "individual stock" if fund.role == "other" and record.get("instrument_type") == "EQUITY"
                       else fund.role, fund.reserve_eligible) for fund, record in zip(funds, records))
    for fund, record in zip(funds, records):
        record["role"] = fund.role
    tickers = tuple(fund.ticker for fund in funds)
    cpi, _, _ = load_cpi_as_known(DEFAULT_DECISION_DATE)
    publication, _, _ = load_first_publication_date(cpi, DEFAULT_DECISION_DATE)
    signal = cpi_signal(cpi, DEFAULT_DECISION_DATE, publication)
    mandate = Mandate("Custom institution", 100_000_000, objective_spread=objective_spread,
                      minimum_reserve_weight=reserve_minimum,
                      reserve_funds=tuple(f.ticker for f in funds if f.reserve_eligible),
                      maximum_fund_weight=.60 if cap_on else None,
                      benchmark_weights=benchmark_weights(funds),
                      max_single_stock_weight=max_single_stock_weight,
                      max_individual_stocks_total=max_individual_stocks_total, min_holdings=min_holdings)
    estimates = estimate_from_monthly_returns(returns, estimate_window, tickers)
    step = .05 if len(funds) <= 5 else .10
    def checker(weights, expected):
        return mandate.check(weights, {"expected_return": expected,
                             "monthly_returns": estimates["monthly_returns"]}, signal["inflation"], funds)
    selected = search_portfolio(estimates, checker, mandate, signal["inflation"], funds, step)
    benchmark = benchmark_weights(funds)
    specifications = [("Equal weight", tuple(1 / len(funds) for _ in funds)), ("60/40 benchmark", benchmark)]
    if selected is not None:
        specifications.append(("Constrained portfolio", selected["weights"]))
    portfolios = []
    for name, weights in specifications:
        expected, volatility = portfolio_metrics(weights, estimates)
        simulation = simulate_portfolio(estimates["monthly_returns"], weights, mandate.objective(signal["inflation"]),
                                        method=simulation_method, seed=seed, mandate=mandate)
        portfolios.append({"name": name, "weights": weight_object(weights, tickers),
                           "dollars": dict(zip(tickers, [weight * mandate.portfolio_size_dollars for weight in weights])),
                           "expected_return": expected, "volatility": volatility,
                           "verdicts": checker(weights, expected),
                           "diversification": diversification_summary(weights, funds),
                           "simulation": {key: value for key, value in simulation.items()
                                          if key not in ("values", "annualized_returns")},
                           "fan_chart_bands": fan_chart_frame(simulation).to_dict("records")})
    if selected is None:
        portfolios.append({"name": "Constrained portfolio", "weights": None, "message": "No mix meets the mandate"})
    frontier = evaluate_frontier(estimates, checker, tickers=tickers, step=step)
    stress = []
    for index, ticker in enumerate(tickers):
        for shift in (-.01, .01):
            changed = dict(estimates)
            values = list(estimates["returns"])
            values[index] += shift
            changed["returns"] = tuple(values)
            mix = search_portfolio(changed, checker, mandate, signal["inflation"], funds, step)
            direction = "lower" if shift < 0 else "higher"
            stress.append({"case": f"{ticker} expected return one point {direction}", "group": "Estimates",
                           "weights": None if mix is None else mix["weights"], "meets_objective": mix is not None})
    stop = stop_summary(stress, selected["weights"] if selected else None, stop_threshold)
    response = {"mandate": asdict(mandate), "rules": None if selected is None else selected["rules"],
                "cpi_signal": {"inflation": signal["inflation"], "month": signal["month"],
                               "first_publication_date": publication, "decision_date": DEFAULT_DECISION_DATE},
                "portfolios": portfolios, "frontier": rounded_frontier(frontier, tickers),
                "backtest": {"table": [], "monthly_series": {}}, "stress": normalize_weight_rows(stress, tickers),
                "stop_condition": stop, "universe": universe_payload(
                    funds, records, returns, step, mandate, selected["method"] if selected else None),
                "mandate_rules": ["Custom universe uses the displayed fund roles and reserve eligibility."],
                "recommendation": {"decided": False}}
    if selected is not None:
        improved = forecast_portfolio(selected["weights"], _forecast_history(returns, estimate_window), funds,
                                      start_value=mandate.portfolio_size_dollars, monthly_flow=-mandate.cash_flow_amount / 3,
                                      months=mandate.horizon_years * 12, method="improved", paths=2_000, seed=seed,
                                      goal=mandate.portfolio_size_dollars)
        improved["chance_of_meeting_objective"] = improved["chance_of_goal"]
        response["improved_forecast"] = improved
    _add_individual_stock_screens(response, funds, DEFAULT_DECISION_DATE.isoformat())
    response["committee"] = committee_report("institution", response)
    return envelope(response)


def custom_personal(request: PersonalRequest, funds: tuple[Fund, ...]) -> dict:
    """Shape the shared personal engine for a custom investment universe."""
    returns, records = load_universe_returns(funds, decision_date=DEFAULT_DECISION_DATE)
    funds = tuple(Fund(fund.ticker, fund.name,
                       "individual stock" if fund.role == "other" and record.get("instrument_type") == "EQUITY"
                       else fund.role, fund.reserve_eligible) for fund, record in zip(funds, records))
    for fund, record in zip(funds, records):
        record["role"] = fund.role
    step = .05 if len(funds) <= 5 else .10
    cpi, _, _ = load_cpi_as_known(DEFAULT_DECISION_DATE)
    publication, _, _ = load_first_publication_date(cpi, DEFAULT_DECISION_DATE)
    signal = cpi_signal(cpi, DEFAULT_DECISION_DATE, publication)
    inputs = _custom_personal_inputs(request)
    result = plan(inputs, returns, signal["inflation"], funds=funds, step=step)
    selected = result["selected"]
    portfolios = result["portfolios"]
    for row in portfolios:
        row["weights"] = weight_object(row.get("weights"), tuple(f.ticker for f in funds))
        if row["weights"] is not None:
            row["diversification"] = diversification_summary(tuple(row["weights"].values()), funds)
    backtest = personal_backtest(inputs, returns, signal["inflation"], result["required_real_return"], funds)
    response = {"inputs": result["inputs"], "emergency_reserve": result["emergency_reserve"],
                "objective": {"inflation": signal["inflation"], "required_real_return": result["required_real_return"],
                              "required_return": result["objective"]},
                "cpi_signal": {"inflation": signal["inflation"], "month": signal["month"],
                               "first_publication_date": publication, "decision_date": DEFAULT_DECISION_DATE},
                "portfolios": portfolios, "frontier": result["frontier"], "backtest": backtest,
                "ways_to_make_it_work": result["ways_to_make_it_work"], "fan_chart": result["fan_chart"],
                "contribution_for_80_percent": result["contribution_for_80_percent"],
                "stress": [], "stop_condition": stop_summary([], selected["weights"] if selected else None, .20),
                "trades": result["trades"], "trade_message": result["trade_message"],
                "policy_statement": result["policy_statement"],
                "universe": universe_payload(
                    funds, records, returns, step, result["mandate"], selected["method"] if selected else None)}
    if selected is None:
        response["fan_chart_note"] = "A fan chart is unavailable because no mix meets the mandate."
        response["contribution_for_80_percent_note"] = (
            "An 80% contribution estimate is unavailable because no mix meets the mandate.")
    else:
        improved = forecast_portfolio(selected["weights"], returns, funds,
                                      start_value=result["emergency_reserve"]["invested_starting_amount"],
                                      monthly_flow=inputs.monthly_contribution, months=inputs.years * 12,
                                      method="improved", paths=2_000, seed=inputs.seed, real=True,
                                      inflation=signal["inflation"], goal=inputs.goal)
        improved["chance_of_reaching_goal_in_todays_dollars"] = improved["chance_of_goal"]
        response["improved_forecast"] = improved
    _add_individual_stock_screens(response, funds, DEFAULT_DECISION_DATE.isoformat())
    response["committee"] = committee_report("personal", response)
    return envelope(response)


def _custom_personal_inputs(request: PersonalRequest) -> PersonalInputs:
    """Create the shared savings input record for custom-universe simulations."""
    return PersonalInputs(savings=request.savings, monthly_contribution=request.monthly_contribution,
                          goal=request.goal, years=request.years, tolerated_drop=request.tolerated_drop,
                          monthly_expenses=request.monthly_expenses, reserve_months=request.reserve_months,
                          other_cash=request.other_cash,
                          trading_cost_basis_points=request.trading_cost_basis_points, seed=request.seed,
                          max_single_stock_weight=request.max_single_stock_weight,
                          max_individual_stocks_total=request.max_individual_stocks_total,
                          min_holdings=request.min_holdings)


def _custom_personal_backtest(request: PersonalRequest, returns: pd.DataFrame, funds: tuple[Fund, ...],
                              plan_weights) -> dict:
    """Backtest custom plans using each selected mix unchanged through realized months."""
    tickers = tuple(fund.ticker for fund in funds)
    values = returns.loc[:, list(tickers)].reset_index(drop=True)
    months = pd.to_datetime(returns["month"]).reset_index(drop=True)
    available_years = max(0, (len(values) - 36) // 12)
    years = min(request.years, available_years)
    if years == 0:
        return {"message": "Not enough history for a 36-month warm-up backtest.",
                "values_are": "actual dollars", "monthly_values": {}, "plan_weights": [], "summary": []}
    inputs = _custom_personal_inputs(request)
    reserve = emergency_reserve(inputs)
    start, end = 35, min(len(values) - 1, 35 + years * 12)
    equal = np.full(len(tickers), 1 / len(tickers))
    benchmark = np.asarray(benchmark_weights(funds))
    mixes = {"Equal weight": equal, "60/40 benchmark": benchmark}
    if plan_weights is not None:
        mixes = {"Your plan": np.asarray(plan_weights), **mixes}
    balances = {name: reserve["invested_starting_amount"] for name in mixes}
    prior_weights = {name: None for name in mixes}
    histories = {name: [] for name in mixes}
    plan_weight_rows = []
    for index in range(start, end):
        asset_returns = values.iloc[index + 1].to_numpy(float)
        for name, weights in mixes.items():
            turnover = (0.0 if prior_weights[name] is None else
                        float(np.abs(weights - prior_weights[name]).sum() / 2))
            gross = float(asset_returns @ weights)
            balances[name] *= 1 + gross - turnover * request.trading_cost_basis_points / 10_000
            if reserve["months_to_fund"] is not None and index - start + 1 > reserve["months_to_fund"]:
                balances[name] += request.monthly_contribution
            histories[name].append({"month": months.iloc[index + 1], "value": balances[name], "turnover": turnover})
            prior_weights[name] = weights * (1 + asset_returns) / (1 + gross)
        if plan_weights is not None:
            plan_weight_rows.append({"month": months.iloc[index + 1], **dict(zip(tickers, plan_weights))})
    contributed = max(0, end - start - (reserve["months_to_fund"] or 0)) * request.monthly_contribution
    summary = []
    for name, history in histories.items():
        path = np.asarray([row["value"] for row in history])
        summary.append({"portfolio": name, "ending_value": float(balances[name]),
                        "total_contributed": float(contributed),
                        "worst_peak_to_trough_drop": float((path / np.maximum.accumulate(path) - 1).min()),
                        "objective_not_reachable_months": 0,
                        "average_turnover": float(np.mean([row["turnover"] for row in history]))})
    return {"values_are": "actual dollars", "monthly_values": histories, "plan_weights": plan_weight_rows,
            "total_contributed": contributed, "ending_values": balances, "summary": summary,
            "years_covered": years}


@app.get("/api/health")
def health():
    """Provide a tiny availability check."""
    return envelope({"status": "ok"})


@app.get("/api/universe/lookup")
def universe_lookup(ticker: str):
    """Look up one Yahoo ticker and save its monthly prices for later offline use."""
    try:
        value = normalize_ticker(ticker)
        role = guessed_role(value)
        fund = Fund(value, "", role, role in ("cash", "government bonds"))
        record = universe_details((fund,))[0]
        if role == "other" and record.get("instrument_type") == "EQUITY":
            record["role"] = "individual stock"
        return envelope(record)
    except ValueError as error:
        message = str(error)
        if "404" in message or "not recognize" in message:
            message = f"Yahoo Finance does not recognize the ticker {ticker.strip().upper()}."
        elif "HTTP Error" in message or "URL" in message or "timed out" in message.lower():
            message = "Yahoo Finance is unavailable right now. Please try again."
        raise HTTPException(422, message) from error


@app.get("/api/universe/default")
def default_universe():
    """Return the four funds used when a request does not choose its own universe."""
    returns, _ = load_monthly_returns()
    return envelope({"funds": [{"ticker": fund.ticker, "name": fund.ticker, "role": fund.role,
                      "reserve_eligible": fund.reserve_eligible,
                      "first_month": returns["month"].iloc[0].date().isoformat(),
                      "last_month": returns["month"].iloc[-1].date().isoformat(), "downloaded_at": None}
                     for fund in DEFAULT_UNIVERSE]})


class RefreshRequest(BaseModel):
    """Validate a request to refresh locally cached Yahoo prices."""

    tickers: list[str]


def _legend_holdings(key: str, as_of: str) -> dict:
    """Load the disclosed holdings and attach the public legend identity."""
    identity = _legend(key)
    portfolio = legends.load_holdings(identity["cik"], as_of)
    return {**portfolio, "person": identity["person"]}


@app.get("/api/legends")
def legend_list(as_of: str = DEFAULT_DECISION_DATE.isoformat()):
    """List the latest filings publicly available on the requested decision date."""
    try:
        return envelope({key: _legend_summary(key, as_of) for key in LEGEND_KEYS})
    except (ValueError, RuntimeError) as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/legends/{key}")
def legend_detail(key: str, as_of: str = DEFAULT_DECISION_DATE.isoformat(), top_n: int = 10):
    """Serve one 13F portfolio and point-in-time quality screens for its largest stocks."""
    if top_n < 1:
        raise HTTPException(422, "top_n must be at least 1.")
    try:
        portfolio = _legend_holdings(key, as_of)
        holdings = portfolio["holdings"]
        return envelope({"summary": _legend_summary(key, as_of),
                         "holdings": [_holding_payload(row) for row in holdings],
                         "options": [_holding_payload(row) for row in portfolio["options"]],
                         "unmapped_cusips": portfolio["unmapped_cusips"],
                         "screens": [_screen_cached(row["ticker"], as_of)
                                     for row in holdings if row.get("ticker")][:top_n]})
    except (ValueError, RuntimeError) as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/legends/{key}/universe")
def legend_universe(key: str, as_of: str = DEFAULT_DECISION_DATE.isoformat(), top_n: int = 10):
    """Return 13F stocks in the custom-universe shape accepted by Compass plans."""
    if top_n < 1:
        raise HTTPException(422, "top_n must be at least 1.")
    try:
        portfolio = _legend_holdings(key, as_of)
        rows = [{"ticker": row["ticker"], "role": "individual stock", "reserve_eligible": False,
                 "weight": row["weight"]} for row in portfolio["holdings"] if row.get("ticker")][:top_n]
        return envelope({"universe": rows,
                         "suggestion": "A plan also needs cash and government bond funds. Add SGOV (cash) and IEF (government bonds).",
                         "suggested_additions": [
                             {"ticker": "SGOV", "role": "cash", "reserve_eligible": True},
                             {"ticker": "IEF", "role": "government bonds", "reserve_eligible": True},
                         ]})
    except (ValueError, RuntimeError) as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/legends/{key}/analysis")
def legend_analysis(key: str, as_of: str = DEFAULT_DECISION_DATE.isoformat(), top_n: int = 10):
    """Analyze disclosed weights as a fixed, point-in-time Meridian-sized portfolio."""
    if top_n < 1:
        raise HTTPException(422, "top_n must be at least 1.")
    try:
        portfolio = _legend_holdings(key, as_of)
        holdings = [row for row in portfolio["holdings"] if row.get("ticker")][:top_n]
        if not holdings:
            raise ValueError("The filing has no mapped stock holdings to analyze.")
        funds = tuple(Fund(row["ticker"], row["issuer"], "individual stock", False) for row in holdings)
        raw_weights = np.asarray([row["weight"] for row in holdings], dtype=float)
        weights = tuple(raw_weights / raw_weights.sum())
        returns, records = load_universe_returns(funds, decision_date=date.fromisoformat(as_of))
        tickers = tuple(fund.ticker for fund in funds)
        estimates = estimate_from_monthly_returns(returns, "all history", tickers)
        expected, volatility = portfolio_metrics(weights, estimates)
        worst = mix_statistic(estimates["monthly_returns"], weights)[2]
        cpi, _, _ = load_cpi_as_known(date.fromisoformat(as_of))
        publication, _, _ = load_first_publication_date(cpi, date.fromisoformat(as_of))
        signal = cpi_signal(cpi, date.fromisoformat(as_of), publication)
        mandate = Mandate("Meridian Foundation", 100_000_000, max_single_stock_weight=SUGGESTED_MAX_SINGLE_STOCK_WEIGHT,
                          max_individual_stocks_total=SUGGESTED_MAX_INDIVIDUAL_STOCKS_TOTAL,
                          min_holdings=SUGGESTED_MIN_HOLDINGS)
        verdicts = mandate.check(weights, {"expected_return": expected,
                                           "monthly_returns": estimates["monthly_returns"]}, signal["inflation"], funds)
        simulation = simulate_portfolio(estimates["monthly_returns"], weights, mandate.objective(signal["inflation"]),
                                        seed=439, mandate=mandate)
        return envelope({"summary": _legend_summary(key, as_of), "weights": weight_object(weights, tickers),
                         "expected_return": expected, "volatility": volatility, "worst_12_month_return": worst,
                         "effective_number_of_holdings": 1 / sum(weight ** 2 for weight in weights),
                         "verdicts": verdicts, "simulation": {name: value for name, value in simulation.items()
                                                                    if name not in ("values", "annualized_returns")},
                         "universe": universe_payload(funds, records, returns, .05, mandate, "fixed 13F weights"),
                         "hindsight_note": f"These weights come from the filing dated {portfolio['filing_date']}. Testing them on earlier years would use information no one had then, so no backtest is shown."})
    except (ValueError, RuntimeError) as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/data/refresh")
def refresh_data(request: RefreshRequest):
    """Refresh selected Yahoo files and rebuild the legacy return file when needed."""
    try:
        funds = tuple(Fund(normalize_ticker(value), "", guessed_role(normalize_ticker(value)),
                           guessed_role(normalize_ticker(value)) in ("cash", "government bonds"))
                      for value in request.tickers)
        if not funds:
            raise ValueError("Provide at least one ticker to refresh.")
        records = universe_details(funds, refresh=True)
        if {fund.ticker for fund in funds} >= {fund.ticker for fund in DEFAULT_UNIVERSE}:
            frame = __import__("data").download_monthly_returns()
            frame.to_csv(__import__("data").MONTHLY_RETURNS_FILE, index=False)
        institution_cached.cache_clear()
        personal_cached.cache_clear()
        return envelope({"funds": records})
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@lru_cache(maxsize=16)
def institution_cached(cap_on: bool = True, reserve_minimum: float = .03, objective_spread: float = .04,
                       estimate_window: str = "all history", stop_threshold: float = .20,
                       backtest_cost: float = 10., simulation_method: str = "Historical bootstrap",
                       seed: int = 439):
    """Calculate and cache the complete institution response."""
    returns, _ = load_monthly_returns()
    cpi, _, _ = load_cpi_as_known(DEFAULT_DECISION_DATE)
    publication, _, _ = load_first_publication_date(cpi, DEFAULT_DECISION_DATE)
    signal = cpi_signal(cpi, DEFAULT_DECISION_DATE, publication)
    inflation = signal["inflation"]
    mandate = Mandate("Meridian Foundation", 100_000_000, objective_spread=objective_spread,
                      minimum_reserve_weight=reserve_minimum, maximum_fund_weight=.60 if cap_on else None)
    estimates = estimate_from_monthly_returns(returns, estimate_window)
    def checker(weights, expected):
        estimate = {"expected_return": expected, "monthly_returns": estimates["monthly_returns"]}
        return mandate.check(weights, estimate, inflation)
    selected = search_lowest_volatility(estimates, checker)
    specifications = [("Equal weight", (.25,) * 4), ("60/40 benchmark", BENCHMARK_WEIGHTS)]
    if selected is not None:
        specifications.append(("Constrained portfolio", selected["weights"]))
    portfolios = []
    for name, weights in specifications:
        expected, volatility = portfolio_metrics(weights, estimates)
        simulation = simulate_portfolio(estimates["monthly_returns"], weights, mandate.objective(inflation),
                                        method=simulation_method, seed=seed, mandate=mandate)
        portfolio = {"name": name, "weights": weight_object(weights),
                     "dollars": dict(zip(FUNDS, [weight * mandate.portfolio_size_dollars for weight in weights])),
                     "expected_return": expected, "volatility": volatility, "verdicts": checker(weights, expected),
                     "simulation": {key: value for key, value in simulation.items()
                                    if key not in ("values", "annualized_returns")},
                     "fan_chart_bands": fan_chart_frame(simulation).to_dict("records")}
        if name == "Constrained portfolio":
            portfolio["worst_12_month_return"] = mix_statistic(returns.loc[:, list(FUNDS)], weights)[2]
        portfolios.append(portfolio)
    if selected is None:
        portfolios.append({"name": "Constrained portfolio", "weights": None,
                           "message": "No mix meets the mandate"})
    frontier = evaluate_frontier(estimates, checker)
    stress_base = selected["weights"] if selected else None
    stress = run_stress(returns, inflation, stress_base, objective_spread)
    backtest = run_backtest(returns, trading_cost_basis_points=backtest_cost)
    recommendation_fields = {name.lower(): getattr(recommendation, name) for name in
                             ("ACTION", "ALLOCATION_RANGE", "CONDITIONS", "TRIGGERS", "COMMITTEE_ASK")}
    placeholders = [str(value) for value in recommendation_fields.values()]
    recommendation_fields["decided"] = not any("To be decided" in value for value in placeholders)
    response = {"mandate": asdict(mandate), "rules": None if selected is None else selected["rules"],
                     "cpi_signal": {"inflation": signal["inflation"], "month": signal["month"],
                                    "first_publication_date": publication,
                                    "decision_date": DEFAULT_DECISION_DATE},
                     "data_card": {"cpi": Path("docs/data-card.md").read_text(encoding="utf-8"),
                                   "prices": Path("docs/data-card-prices.md").read_text(encoding="utf-8")},
                     "mandate_rules": institution_mandate_rules(mandate),
                     "recommendation": recommendation_fields, "locked_record": locked_record(),
                     "portfolios": portfolios, "frontier": rounded_frontier(frontier),
                     "backtest": {"table": backtest["summary"], "monthly_series": backtest["histories"]},
                     "stress": normalize_weight_rows(stress),
                     "stop_condition": stop_summary(stress, stress_base, stop_threshold)}
    default_records = [{"ticker": fund.ticker, "name": fund.ticker, "role": fund.role,
                        "reserve_eligible": fund.reserve_eligible,
                        "first_month": returns["month"].iloc[0].date().isoformat(),
                        "last_month": returns["month"].iloc[-1].date().isoformat(), "downloaded_at": None}
                       for fund in DEFAULT_UNIVERSE]
    response["universe"] = universe_payload(DEFAULT_UNIVERSE, default_records, returns, .05)
    if selected is not None:
        improved = forecast_portfolio(selected["weights"], _forecast_history(returns, estimate_window), DEFAULT_UNIVERSE,
                                      start_value=mandate.portfolio_size_dollars, monthly_flow=-mandate.cash_flow_amount / 3,
                                      months=mandate.horizon_years * 12, method="improved", paths=2_000, seed=seed,
                                      goal=mandate.portfolio_size_dollars)
        improved["chance_of_meeting_objective"] = improved["chance_of_goal"]
        response["improved_forecast"] = improved
    response["committee"] = committee_report("institution", response)
    return envelope(response)


@app.get("/api/institution")
def institution(cap_on: bool = True, reserve_minimum: float = .03, objective_spread: float = .04,
                estimate_window: str = "all history", stop_threshold: float = .20,
                backtest_cost: float = 10., simulation_method: str = "Historical bootstrap", seed: int = 439,
                tickers: str | None = None, reserve: str | None = None, roles: str | None = None,
                max_single_stock_weight: float | None = None, max_individual_stocks_total: float | None = None,
                min_holdings: int | None = None):
    """Serve the institution analysis with readable validation errors."""
    if not 0 <= reserve_minimum <= 1:
        raise HTTPException(422, "Reserve minimum must be between 0% and 100%.")
    if objective_spread < 0 or not 0 <= stop_threshold <= 1:
        raise HTTPException(422, "Objective spread and stop threshold must be non-negative percentages.")
    try:
        if tickers:
            role_map = dict(item.split(":", 1) for item in roles.split(",") if ":" in item) if roles else {}
            reserve_set = {item.strip().upper() for item in reserve.split(",")} if reserve else None
            funds = make_funds([{"ticker": item, "role": role_map.get(item.strip().upper()),
                                 "reserve_eligible": item.strip().upper() in reserve_set if reserve_set is not None else None}
                                for item in tickers.split(",")])
            if not is_default(funds):
                return custom_institution(funds, cap_on, reserve_minimum, objective_spread, estimate_window,
                                          stop_threshold, simulation_method, seed, max_single_stock_weight,
                                          max_individual_stocks_total, min_holdings)
        return institution_cached(cap_on, reserve_minimum, objective_spread, estimate_window,
                                  stop_threshold, backtest_cost, simulation_method, seed)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


def personal_stress(result: dict, inputs: PersonalInputs, returns: pd.DataFrame, inflation: float,
                    threshold: float = .20) -> tuple[list[dict], dict]:
    """Run personal-rule stress cases and summarize the required stop condition."""
    statistics = result["statistics"]
    base = result["selected"]
    base_weights = base["weights"] if base else None
    rows = []
    for fund_index, fund in enumerate(FUNDS):
        for shift in (-.01, .01):
            changed = dict(statistics)
            changed["expected_return"] = statistics["expected_return"] + statistics["weights"][:, fund_index] * shift
            mix = choose_personal_mix(changed, result["objective"], inputs.tolerated_drop)
            direction = "lower" if shift < 0 else "higher"
            rows.append({"case": f"{fund} expected return one point {direction}", "group": "Estimates",
                         "weights": None if mix is None else mix["weights"], "meets_objective": mix is not None})
    for drop in (max(0, inputs.tolerated_drop - .05), min(1, inputs.tolerated_drop + .05)):
        mix = choose_personal_mix(statistics, result["objective"], drop)
        direction = "lower" if drop < inputs.tolerated_drop else "higher"
        points = abs(drop - inputs.tolerated_drop)
        rows.append({"case": f"Tolerated drop {points * 100:.0f} points {direction} ({drop:.0%})", "group": "Rules",
                     "weights": None if mix is None else mix["weights"], "meets_objective": mix is not None})
    for contribution in (inputs.monthly_contribution * .90, inputs.monthly_contribution * 1.10):
        reserve = result["emergency_reserve"]
        required = required_real_return(reserve["invested_starting_amount"], contribution, inputs.goal, inputs.years,
                                        reserve["months_to_fund"] or 0)
        objective = None if required is None else required + (result["objective"] - result["required_real_return"] if result["required_real_return"] is not None else 0)
        mix = choose_personal_mix(statistics, objective, inputs.tolerated_drop)
        direction = "lower" if contribution < inputs.monthly_contribution else "higher"
        rows.append({"case": f"Monthly contribution 10% {direction} (${contribution:,.0f})", "group": "Rules",
                     "weights": None if mix is None else mix["weights"], "meets_objective": mix is not None})
    for months in (60, 36):
        from mixes import mix_statistics
        window_statistics = mix_statistics(returns.loc[:, list(FUNDS)].tail(months))
        mix = choose_personal_mix(window_statistics, result["objective"], inputs.tolerated_drop)
        rows.append({"case": f"Estimate window: last {months} months", "group": "Data window", "weights": None if mix is None else mix["weights"],
                     "meets_objective": mix is not None})
    for cost in (0, 10, 25, 50):
        label = f"Trading cost {cost} basis points"
        rows.append({"case": label, "group": "Costs", "weights": base_weights, "meets_objective": base is not None})
    return rows, stop_summary(rows, base_weights, threshold)


@lru_cache(maxsize=32)
def personal_cached(raw: str):
    """Calculate and cache a personal response keyed by validated request JSON."""
    request = json.loads(raw)
    request.pop("universe", None)
    request.pop("max_single_stock_weight", None)
    request.pop("max_individual_stocks_total", None)
    request.pop("min_holdings", None)
    holdings = request.pop("holdings", None)
    values = tuple((holdings or {}).get(fund, 0.0) for fund in FUNDS) if holdings is not None else None
    inputs = PersonalInputs(**request, holdings=values)
    returns, _ = load_monthly_returns()
    cpi, _, _ = load_cpi_as_known(DEFAULT_DECISION_DATE)
    publication, _, _ = load_first_publication_date(cpi, DEFAULT_DECISION_DATE)
    personal_signal = cpi_signal(cpi, DEFAULT_DECISION_DATE, publication)
    inflation = personal_signal["inflation"]
    result = plan(inputs, returns, inflation)
    stress, stop = personal_stress(result, inputs, returns, inflation)
    portfolios = normalize_weight_rows(result["portfolios"])
    for portfolio in portfolios:
        weights = portfolio.get("weights")
        portfolio["diversification"] = diversification_summary(
            None if weights is None else tuple(weights.values()), DEFAULT_UNIVERSE)
    response = {"inputs": result["inputs"], "emergency_reserve": result["emergency_reserve"],
                "objective": {"inflation": inflation, "required_real_return": result["required_real_return"],
                              "required_return": result["objective"]},
                "cpi_signal": {"inflation": personal_signal["inflation"], "month": personal_signal["month"],
                               "first_publication_date": publication, "decision_date": DEFAULT_DECISION_DATE},
                "portfolios": portfolios,
                "ways_to_make_it_work": result["ways_to_make_it_work"], "fan_chart": result["fan_chart"],
                "contribution_for_80_percent": result["contribution_for_80_percent"],
                "backtest": personal_backtest(inputs, returns, inflation, result["required_real_return"]),
                "stress": normalize_weight_rows(stress),
                "stop_condition": stop, "trades": result["trades"], "trade_message": result["trade_message"],
                "policy_statement": result["policy_statement"], "frontier": rounded_frontier(result["frontier"])}
    default_records = [{"ticker": fund.ticker, "name": fund.ticker, "role": fund.role,
                        "reserve_eligible": fund.reserve_eligible,
                        "first_month": returns["month"].iloc[0].date().isoformat(),
                        "last_month": returns["month"].iloc[-1].date().isoformat(), "downloaded_at": None}
                       for fund in DEFAULT_UNIVERSE]
    response["universe"] = universe_payload(DEFAULT_UNIVERSE, default_records, returns, .05)
    if result["selected"] is not None:
        improved = forecast_portfolio(result["selected"]["weights"], returns, DEFAULT_UNIVERSE,
                                      start_value=result["emergency_reserve"]["invested_starting_amount"],
                                      monthly_flow=inputs.monthly_contribution, months=inputs.years * 12,
                                      method="improved", paths=2_000, seed=inputs.seed, real=True,
                                      inflation=inflation, goal=inputs.goal)
        improved["chance_of_reaching_goal_in_todays_dollars"] = improved["chance_of_goal"]
        response["improved_forecast"] = improved
    response["committee"] = committee_report("personal", response)
    return envelope(response)


@app.post("/api/personal/plan")
def personal_endpoint(request: PersonalRequest):
    """Serve a validated personal investment plan."""
    if request.holdings is not None:
        unknown = set(request.holdings) - set(FUNDS)
        negative = [fund for fund, value in request.holdings.items() if value < 0]
        if unknown or negative:
            raise HTTPException(422, "Holdings must use known fund tickers and cannot be negative.")
    try:
        if request.universe is not None:
            funds = make_funds(request.universe)
            if not is_default(funds):
                return custom_personal(request, funds)
        return personal_cached(request.model_dump_json())
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


def _analysis_inputs(holdings: dict[str, float], roles: dict[str, str] | None):
    """Load a role-described analysis universe using the existing saved-price path."""
    if not holdings or any(value < 0 for value in holdings.values()):
        raise ValueError("Holdings must be non-negative and include at least one value.")
    funds = make_funds([{"ticker": ticker, "role": (roles or {}).get(ticker.upper())} for ticker in holdings])
    if is_default(funds):
        returns, _ = load_monthly_returns()
        crisis_returns = returns
    else:
        returns, _ = load_universe_returns(funds, decision_date=DEFAULT_DECISION_DATE)
        crisis_returns = load_crisis_reference_returns(funds, decision_date=DEFAULT_DECISION_DATE)
    normalized = {normalize_ticker(ticker): value for ticker, value in holdings.items()}
    return normalized, funds, returns, crisis_returns


@app.post("/api/analyze")
def analyze_endpoint(request: PortfolioAnalysisRequest):
    """Return additive portfolio diagnostics without changing existing plan responses."""
    try:
        holdings, funds, returns, crisis_returns = _analysis_inputs(request.holdings, request.roles)
        return envelope(analyze_portfolio(holdings, funds, returns, horizon_years=request.horizon_years,
                                          monthly_flow=request.monthly_flow, crisis_returns=crisis_returns))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/compare")
def compare_endpoint(request: PortfolioCompareRequest):
    """Return a side-by-side comparison for two portfolios sharing a universe."""
    try:
        holdings = {**request.a, **request.b}
        _, funds, returns, crisis_returns = _analysis_inputs(holdings, request.roles)
        a = {normalize_ticker(ticker): value for ticker, value in request.a.items()}
        b = {normalize_ticker(ticker): value for ticker, value in request.b.items()}
        return envelope(compare_portfolios(a, b, funds, returns, horizon_years=request.horizon_years,
                                           crisis_returns=crisis_returns))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/calibration")
def calibration_endpoint(request: CalibrationRequest):
    """Run or reuse a saved walk-forward calibration report."""
    try:
        holdings = request.holdings
        tickers = request.tickers or (list(holdings) if holdings else None)
        if not tickers:
            raise ValueError("Provide holdings or tickers.")
        weights = request.weights
        if weights is None:
            if holdings is None:
                raise ValueError("Provide weights when using tickers without holdings.")
            values = np.asarray([holdings[ticker] for ticker in tickers], dtype=float)
            if values.sum() <= 0:
                raise ValueError("Holdings must total more than zero.")
            weights = values / values.sum()
        if len(weights) != len(tickers):
            raise ValueError("Weights must have one value for each ticker.")
        roles = request.roles
        _, funds, returns, _ = _analysis_inputs({ticker: 1.0 for ticker in tickers}, roles)
        return envelope(calibration_test(weights, returns, funds))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/risk-profile/questions")
def risk_profile_questions():
    """Serve the five renderable risk-profile questions."""
    return envelope({"questions": QUESTIONS})


@app.post("/api/risk-profile")
def risk_profile_endpoint(request: RiskProfileRequest):
    try:
        return envelope(risk_profile(request.answers))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/committee/live")
def committee_live(request: CommitteeLiveRequest):
    """Rebuild a response on the server before requesting optional live reviews."""
    try:
        if request.mode == "institution":
            settings = request.settings or {}
            allowed = {"cap_on", "reserve_minimum", "objective_spread", "estimate_window", "stop_threshold",
                       "backtest_cost", "simulation_method", "seed"}
            if set(settings) - allowed:
                raise ValueError("Institution settings include an unknown field.")
            payload = institution_cached(**settings)
        elif request.mode == "personal":
            if request.inputs is None:
                raise ValueError("Personal live review needs inputs.")
            personal_request = PersonalRequest(**request.inputs)
            if personal_request.holdings is not None:
                unknown = set(personal_request.holdings) - set(FUNDS)
                negative = [fund for fund, value in personal_request.holdings.items() if value < 0]
                if unknown or negative:
                    raise ValueError("Holdings must use known fund tickers and cannot be negative.")
            payload = personal_cached(personal_request.model_dump_json())
        else:
            raise ValueError("Committee mode must be institution or personal.")
        committee = committee_report(request.mode, payload, live=True)
        committee["model"] = "claude-opus-5-5"
        return committee
    except RuntimeError as error:
        raise HTTPException(503, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


# Ask Compass (optional AI assistant, built by Claude). Registered before the website so /api/assistant/* is reachable.
from assistant import router as assistant_router  # noqa: E402
app.include_router(assistant_router)


@app.middleware("http")
async def always_check_for_new_website_files(request, call_next):
    """Tell the browser to re-check website files on every load, so an update never shows a stale page."""
    response = await call_next(request)
    if not request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-cache"
    return response


app.mount("/files/docs", StaticFiles(directory="docs"), name="files-docs")
app.mount("/", StaticFiles(directory="web", html=True), name="web")
