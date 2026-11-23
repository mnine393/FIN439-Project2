"""Write reviewer-readable Endowment Command Center output without the web application."""
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
import pandas as pd
from backtest import run_backtest
from committee import committee_report
from cpi_signal import DEFAULT_DECISION_DATE, cpi_signal, load_cpi_as_known, load_first_publication_date
from data import load_monthly_returns
from forecast import calibration_test, forecast_portfolio
from frontier import evaluate_frontier
from mandate import BENCHMARK_WEIGHTS, FUNDS, Mandate, PORTFOLIO_SIZE_DOLLARS, QUARTERLY_PAYOUT_DOLLARS, check_portfolio
from portfolio import estimate_from_monthly_returns, portfolio_metrics, search_lowest_volatility
from simulation import simulate_portfolio
from server import stop_summary
from stress import run_stress
from personal import PersonalInputs, plan
import recommendation
from universe import DEFAULT_UNIVERSE

def money(value): return "not applicable" if pd.isna(value) else f"${value:,.0f}"
def rate(value): return "not applicable" if pd.isna(value) else f"{value:.2%}"
def show_weights(weights, invested_amount=PORTFOLIO_SIZE_DOLLARS): return ", ".join(f"{n} {rate(w)} ({money(w * invested_amount)})" for n, w in zip(FUNDS, weights))
def markdown_table(frame):
    frame = frame.copy()
    for column in frame:
        name = column.lower()
        if (any(word in name for word in ("return", "volatility", "drop", "turnover", "probability", "weight", "change", "chance", "share"))
                or name in ("below", "above")):
            frame[column] = frame[column].map(rate)
        elif any(word in name for word in ("value", "dollars", "percentile")):
            frame[column] = frame[column].map(money)
    frame = frame.fillna("not applicable")
    columns = list(frame.columns)
    rows = ["| " + " | ".join(map(str, columns)) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    rows += ["| " + " | ".join(map(str, row)) + " |" for row in frame.itertuples(index=False, name=None)]
    return "\n".join(rows)

def main():
    returns, downloaded = load_monthly_returns()
    cpi, location, _ = load_cpi_as_known(DEFAULT_DECISION_DATE)
    publication, publication_location, _ = load_first_publication_date(cpi, DEFAULT_DECISION_DATE)
    signal = cpi_signal(cpi, DEFAULT_DECISION_DATE, publication); inflation = signal["inflation"]
    estimates = estimate_from_monthly_returns(returns)
    constrained = search_lowest_volatility(estimates, lambda w, r: check_portfolio(w, r, inflation))
    portfolios = [("Equal weight", (.25,) * 4), ("60/40 benchmark", BENCHMARK_WEIGHTS)] + ([("Constrained portfolio", constrained["weights"])] if constrained else [])
    output = ["# FIN 439 Project 2 visible output", "", "## Material inputs", f"Decision date: {DEFAULT_DECISION_DATE}",
              f"Return file: data/monthly_returns.csv; funds: {', '.join(FUNDS)}", "Estimates use all monthly returns.",
              f"Portfolio size: ${PORTFOLIO_SIZE_DOLLARS:,.0f}; quarterly payout: ${QUARTERLY_PAYOUT_DOLLARS:,.0f}.",
              "The 3% reserve rule equals four quarterly payouts divided by portfolio size.", "", "## Consumer Price Index as known",
              f"Consumer Price Index year-over-year: {rate(inflation)}", f"Latest known month: {signal['month']}", f"First published: {publication}", f"Saved file: {location}", "", "## Portfolios"]
    for name, weights in portfolios:
        expected, volatility = portfolio_metrics(weights, estimates)
        output += [f"### {name}", f"Weights: {show_weights(weights)}", f"Expected return: {rate(expected)}", f"Volatility: {rate(volatility)}"]
    stress_rows = []
    if constrained:
        stress_rows = run_stress(returns, inflation, constrained["weights"], .04)
        output += ["", "## Stress"]
        output += [markdown_table(pd.DataFrame(stress_rows).drop(columns=["weights"]))]
    frontier = evaluate_frontier(estimates, lambda w, r: check_portfolio(w, r, inflation))
    output += ["", "## Frontier summary", f"Mixes evaluated: {len(frontier):,}", f"Mixes meeting every mandate rule: {int(frontier['meets_mandate'].sum()):,}"]
    output += ["", "## Monte Carlo table"]
    simulation_rows = []
    for name, weights in portfolios:
        result = simulate_portfolio(estimates["monthly_returns"], weights, inflation + .04)
        simulation_rows.append({"portfolio": name, "probability objective": result["probability_objective"], "probability below $90m": result["probability_below_90m"], "median ending value": result["median_ending_value"], "5th percentile": result["p5_ending_value"], "95th percentile": result["p95_ending_value"]})
    output += [markdown_table(pd.DataFrame(simulation_rows))]
    backtest = run_backtest(returns)
    output += ["", "## Backtest table"]
    output += [markdown_table(backtest["summary"])]
    person = PersonalInputs(40_000, 1_200, 1_000_000, 30, .40, 3_000, 6)
    personal_result = plan(person, returns, inflation)
    output += ["", "## Personal mode example", "Example: $40,000 savings, $1,200 monthly contribution, $1,000,000 goal, 30 years, 40% tolerated drop, $3,000 monthly expenses, and six reserve months."]
    if personal_result["portfolios"]:
        selected = personal_result["portfolios"][0]
        output += [f"Suggested portfolio: {selected['name']}; expected return {rate(selected['expected_return'])}; volatility {rate(selected['volatility'])}."]
        if selected.get("weights") is not None:
            output += [f"Chance of reaching the goal: {rate(selected['simulation']['chance_of_goal'])}.",
                       f"Mix: {show_weights(selected['weights'], personal_result['emergency_reserve']['invested_starting_amount'])}.",
                       f"Monthly contribution for an 80% chance: {money(personal_result['contribution_for_80_percent'])}."]

    mandate = Mandate("Meridian Foundation", PORTFOLIO_SIZE_DOLLARS,
                      minimum_reserve_weight=4 * QUARTERLY_PAYOUT_DOLLARS / PORTFOLIO_SIZE_DOLLARS)
    portfolio_rows = []
    for name, weights in portfolios:
        expected, volatility = portfolio_metrics(weights, estimates)
        portfolio_rows.append({"name": name, "weights": dict(zip(FUNDS, weights)),
                               "expected_return": expected, "volatility": volatility,
                               "verdicts": mandate.check(weights, {"expected_return": expected,
                                                                     "monthly_returns": estimates["monthly_returns"]}, inflation),
                               "simulation": simulate_portfolio(estimates["monthly_returns"], weights,
                                                                 mandate.objective(inflation), mandate=mandate)})

    output += ["", "## Mandate verdicts"]
    verdict_rows = []
    for portfolio in portfolio_rows:
        for verdict in portfolio["verdicts"]:
            verdict_rows.append({"portfolio": portfolio["name"], "rule": verdict["rule"],
                                 "verdict": "Pass" if verdict["pass"] else "Fail"})
    output += [markdown_table(pd.DataFrame(verdict_rows))]

    stop = stop_summary(stress_rows, constrained["weights"] if constrained else None, .20)
    output += ["", "## Stop condition", f"Triggered: {'Yes' if stop['triggered'] else 'No'}.",
               f"Threshold: {rate(stop['threshold'])} change in any weight."]
    output += ["Stress cases that triggered it: " + ("; ".join(stop["triggered_cases"]) if stop["triggered_cases"] else "None.")]

    committee_payload = {"mandate": asdict(mandate),
                         "cpi_signal": {"inflation": inflation, "month": signal["month"]},
                         "portfolios": portfolio_rows,
                         "backtest": {"summary": backtest["summary"]}, "stress": stress_rows,
                         "stop_condition": stop,
                         "universe": {"is_default": True,
                                      "funds": [{"ticker": fund.ticker, "role": fund.role}
                                                for fund in DEFAULT_UNIVERSE]}}
    committee = committee_report("institution", committee_payload)
    output += ["", "## Committee review"]
    output += [markdown_table(pd.DataFrame([{"member": member["name"], "vote": member["vote"],
                                             "memo source": member["memo_source"]}
                                            for member in committee["members"]]))]
    output += [f"Outcome: {committee['outcome']}."]

    forecast_rows = []
    forecast_specs = [("Constrained portfolio", constrained["weights"])] if constrained else []
    forecast_specs.append(("60/40 benchmark", BENCHMARK_WEIGHTS))
    for name, weights in forecast_specs:
        forecast = forecast_portfolio(weights, returns, DEFAULT_UNIVERSE,
                                      start_value=PORTFOLIO_SIZE_DOLLARS,
                                      monthly_flow=-QUARTERLY_PAYOUT_DOLLARS / 3, months=7 * 12,
                                      method="improved", paths=2_000, seed=439,
                                      goal=PORTFOLIO_SIZE_DOLLARS)
        ending = forecast["percentiles"]["84"]
        forecast_rows.append({"portfolio": name, "method": forecast["method"],
                              "expected return": forecast["expected_annual_return"],
                              "10th percentile ending value": ending["p10"],
                              "50th percentile ending value": ending["p50"],
                              "90th percentile ending value": ending["p90"],
                              "yield dates": ", ".join(f"{series}: {date}" for series, date in forecast["yield_dates"].items()),
                              "chance of ending at or above $100 million": forecast["chance_of_goal"]})
    output += ["", "## Improved forecast (Build G)",
               "Seven-year forecast using a $750,000 quarterly payout (modeled as a $250,000 monthly outflow)."]
    output += [markdown_table(pd.DataFrame(forecast_rows))]

    calibration = calibration_test(BENCHMARK_WEIGHTS, returns, DEFAULT_UNIVERSE)
    calibration_rows = []
    for method, horizons in calibration["methods"].items():
        for horizon, values in horizons.items():
            calibration_rows.append({"method": method, "horizon (months)": int(horizon),
                                     "number of forecasts": values["number_of_forecasts"],
                                     "share inside the 10th-90th range": values["inside_10_90"],
                                     "below": values["below_10"], "above": values["above_90"],
                                     "pinball loss": f"{values['pinball_loss']:.4f}"})
    output += ["", "## Forecast calibration", "60/40 benchmark (VT 60%, IEF 40%)."]
    output += [markdown_table(pd.DataFrame(calibration_rows))]

    output += ["", "## Recommendation", f"Action: {recommendation.ACTION}",
               f"Allocation range: {recommendation.ALLOCATION_RANGE}",
               f"Conditions: {recommendation.CONDITIONS}", "Triggers:"]
    output += [f"- {trigger}" for trigger in recommendation.TRIGGERS]
    output += [f"Committee ask: {recommendation.COMMITTEE_ASK}"]
    Path("output").mkdir(exist_ok=True); Path("output/visible_output.md").write_text("\n".join(output) + "\n", encoding="utf-8")
    print("Wrote output/visible_output.md")
if __name__ == "__main__": main()
