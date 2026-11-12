"""Write reviewer-readable Endowment Command Center output without the web application."""
from __future__ import annotations
from pathlib import Path
import pandas as pd
from backtest import run_backtest
from cpi_signal import DEFAULT_DECISION_DATE, cpi_signal, load_cpi_as_known, load_first_publication_date
from data import load_monthly_returns
from frontier import evaluate_frontier
from mandate import BENCHMARK_WEIGHTS, FUNDS, PORTFOLIO_SIZE_DOLLARS, QUARTERLY_PAYOUT_DOLLARS, check_portfolio
from portfolio import estimate_from_monthly_returns, portfolio_metrics, search_lowest_volatility
from simulation import simulate_portfolio
from stress import run_stress

def money(value): return "not applicable" if pd.isna(value) else f"${value:,.0f}"
def rate(value): return "not applicable" if pd.isna(value) else f"{value:.2%}"
def show_weights(weights): return ", ".join(f"{n} {rate(w)} ({money(w * PORTFOLIO_SIZE_DOLLARS)})" for n, w in zip(FUNDS, weights))
def markdown_table(frame):
    frame = frame.copy()
    for column in frame:
        name = column.lower()
        if any(word in name for word in ("return", "volatility", "drop", "turnover", "probability", "weight", "change")):
            frame[column] = frame[column].map(rate)
        elif any(word in name for word in ("value", "dollars")):
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
    if constrained:
        output += ["", "## Stress"]
        output += [markdown_table(pd.DataFrame(run_stress(returns, inflation, constrained["weights"], .04)).drop(columns=["weights"]))]
    frontier = evaluate_frontier(estimates, lambda w, r: check_portfolio(w, r, inflation))
    output += ["", "## Frontier summary", f"Mixes evaluated: {len(frontier):,}", f"Mixes meeting every mandate rule: {int(frontier['meets_mandate'].sum()):,}"]
    output += ["", "## Monte Carlo table"]
    simulation_rows = []
    for name, weights in portfolios:
        result = simulate_portfolio(estimates["monthly_returns"], weights, inflation + .04)
        simulation_rows.append({"portfolio": name, "probability objective": result["probability_objective"], "probability below $90m": result["probability_below_90m"], "median ending value": result["median_ending_value"], "5th percentile": result["p5_ending_value"], "95th percentile": result["p95_ending_value"]})
    output += [markdown_table(pd.DataFrame(simulation_rows))]
    output += ["", "## Backtest table"]
    output += [markdown_table(run_backtest(returns)["summary"])]
    Path("output").mkdir(exist_ok=True); Path("output/visible_output.md").write_text("\n".join(output) + "\n", encoding="utf-8")
    print("Wrote output/visible_output.md")
if __name__ == "__main__": main()
