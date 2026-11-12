"""Streamlit interface for the FIN 439 Endowment Command Center."""
from __future__ import annotations
from pathlib import Path
import altair as alt
import pandas as pd
import streamlit as st
from backtest import run_backtest
from cpi_signal import DEFAULT_DECISION_DATE, cpi_signal, load_cpi_as_known, load_first_publication_date
from data import load_monthly_returns
from frontier import evaluate_frontier
from mandate import BENCHMARK_WEIGHTS, FUNDS, PORTFOLIO_SIZE_DOLLARS, QUARTERLY_PAYOUT_DOLLARS, check_portfolio
from portfolio import estimate_from_monthly_returns, portfolio_metrics, search_lowest_volatility
from simulation import fan_chart_frame, simulate_portfolio
from stress import run_stress

AI_STATEMENT = "AI use: built with OpenAI Codex (GPT-5.6-Terra) for the code and Claude for planning and checking; the analysis and the decision are mine."
ADVICE_STATEMENT = "Education, not investment advice."

def weights_text(weights): return " | ".join(f"{f}: {w:.0%} (${w * PORTFOLIO_SIZE_DOLLARS:,.0f})" for f, w in zip(FUNDS, weights))
def verdict_frame(rules): return pd.DataFrame({"Rule": [r["rule"] for r in rules], "Verdict": ["Pass" if r["pass"] else "Fail" for r in rules]})

@st.cache_data(show_spinner=False)
def cached_frontier(returns, inflation, reserve, cap, spread):
    estimates = estimate_from_monthly_returns(returns)
    return evaluate_frontier(estimates, lambda w, r: check_portfolio(w, r, inflation, reserve_minimum=reserve, use_maximum_fund_weight=cap, objective_spread=spread))
@st.cache_data(show_spinner=False)
def cached_simulation(returns, weights, objective, method, seed): return simulate_portfolio(returns, weights, objective, method=method, seed=seed)
@st.cache_data(show_spinner=False)
def cached_backtest(returns, cost): return run_backtest(returns, trading_cost_basis_points=cost)

def main():
    st.set_page_config(page_title="Endowment Command Center", layout="wide")
    st.write(AI_STATEMENT); st.write(ADVICE_STATEMENT); st.title("Endowment Command Center")
    with st.sidebar:
        decision_date = st.date_input("Decision date", DEFAULT_DECISION_DATE)
        window = st.selectbox("Estimate window", ["all history", "last 60 months", "last 36 months"])
        cap = st.toggle("Use the 60% fund cap", value=True)
        reserve = st.number_input("Minimum SGOV + IEF reserve (percent)", 0., 100., 3., 1.) / 100
        spread = st.number_input("Objective spread over inflation (percent)", -100., 100., 4., 1.) / 100
        stop = st.number_input("Stop threshold for a weight change (percent)", 0., 100., 20., 1.) / 100
        cost = st.number_input("Backtest trading cost (basis points)", 0., 100., 10., 1.)
        refresh = st.button("Refresh market data")
    try:
        returns, market_download = load_monthly_returns(refresh)
        cpi, saved, cpi_download = load_cpi_as_known(decision_date)
        publication, publication_saved, publication_download = load_first_publication_date(cpi, decision_date)
        signal = cpi_signal(cpi, decision_date, publication)
    except Exception as error:
        st.error(f"Required offline data is unavailable: {error}"); return
    estimates = estimate_from_monthly_returns(returns, window); inflation = signal["inflation"]; objective = inflation + spread
    checker = lambda w, r: check_portfolio(w, r, inflation, reserve_minimum=reserve, use_maximum_fund_weight=cap, objective_spread=spread)
    constrained = search_lowest_volatility(estimates, checker); equal = (.25,) * 4
    portfolios = [("Equal weight", equal), ("60/40 benchmark", BENCHMARK_WEIGHTS)] + ([("Constrained portfolio", constrained["weights"])] if constrained else [])
    tabs = st.tabs(["Mandate", "Signal", "Portfolios", "Stress", "Frontier", "Will the money last?", "Would it have worked?", "Recommendation"])
    with tabs[0]:
        st.write(f"Objective: at least inflation + {spread:.0%} ({objective:.2%}) each year over seven years.")
        st.write(f"Portfolio size: ${PORTFOLIO_SIZE_DOLLARS:,.0f}; quarterly payout: ${QUARTERLY_PAYOUT_DOLLARS:,.0f}. The 3% reserve rule equals four quarterly payouts divided by portfolio size.")
        st.dataframe(verdict_frame(checker(equal, portfolio_metrics(equal, estimates)[0])), hide_index=True)
    with tabs[1]:
        st.write(f"CPI year-over-year: {inflation:.2%}; latest known month: {signal['month']}; first published (from ALFRED vintages): {signal['publication_date']}.")
        st.caption(f"Market returns: {'Downloaded for this run.' if market_download else 'Used saved copy.'} CPI: {'Downloaded for this run.' if cpi_download else 'Used saved copy.'}")
        st.caption(f"CPI publication-date source: {publication_saved}. {'Downloaded for this run.' if publication_download else 'Used saved copy.'}")
        st.markdown(Path("docs/data-card.md").read_text(encoding="utf-8")); st.markdown(Path("docs/data-card-prices.md").read_text(encoding="utf-8"))
    with tabs[2]:
        for column, (name, weights) in zip(st.columns(3), portfolios):
            expected, volatility = portfolio_metrics(weights, estimates)
            with column:
                st.subheader(name); st.write(weights_text(weights)); st.write(f"Expected return: {expected:.2%}"); st.write(f"Volatility: {volatility:.2%}"); st.dataframe(verdict_frame(checker(weights, expected)), hide_index=True)
        if not constrained: st.error("No mix meets the mandate.")
    with tabs[3]:
        if not constrained: st.error("Stop condition triggered: no mix meets the mandate in the base case. Recommend reject.")
        else:
            rows = run_stress(returns, inflation, constrained["weights"], spread)
            table = pd.DataFrame([{**r, "weights": "No mix meets the mandate" if r["weights"] is None else weights_text(r["weights"])} for r in rows])
            st.dataframe(table, hide_index=True, use_container_width=True)
            triggers = [r["case"] for r in rows if r["weights"] is None or r["largest_weight_change"] > stop]
            st.error("Stop condition triggered. Recommend reject: " + "; ".join(triggers)) if triggers else st.success("Stop condition not triggered.")
    with tabs[4]:
        frontier = cached_frontier(returns.loc[:, list(FUNDS)], inflation, reserve, cap, spread)
        chart = alt.Chart(frontier).mark_circle(size=45).encode(x=alt.X("volatility:Q", title="Annual volatility", axis=alt.Axis(format="%")), y=alt.Y("expected_return:Q", title="Expected annual return", axis=alt.Axis(format="%")), color=alt.condition("datum.meets_mandate", alt.value("#1677b8"), alt.value("#cccccc")), opacity=alt.condition("datum.meets_mandate", alt.value(.9), alt.value(.25)), tooltip=[alt.Tooltip(f"{f}:Q", format=".0%") for f in FUNDS])
        objective_line = alt.Chart(pd.DataFrame({"objective": [objective]})).mark_rule(color="firebrick").encode(y="objective:Q")
        labels = pd.DataFrame([{"name": n, "volatility": portfolio_metrics(w, estimates)[1], "expected_return": portfolio_metrics(w, estimates)[0]} for n, w in portfolios])
        points = alt.Chart(labels).mark_point(shape="diamond", color="black", size=130).encode(x="volatility:Q", y="expected_return:Q") + alt.Chart(labels).mark_text(align="left", dx=7, dy=-7).encode(x="volatility:Q", y="expected_return:Q", text="name:N")
        st.altair_chart(chart + objective_line + points, use_container_width=True); st.caption(f"{len(frontier):,} five-percentage-point long-only mixes. Blue mixes meet every mandate rule.")
    with tabs[5]:
        method = st.selectbox("Simulation method", ["Historical bootstrap", "Normal distribution"]); seed = int(st.number_input("Random seed", 0, 2147483647, 439, 1))
        selected = st.selectbox("Portfolio for fan chart", [n for n, _ in portfolios]); selected_weights = dict(portfolios)[selected]
        result = cached_simulation(estimates["monthly_returns"], selected_weights, objective, method, seed); fan = fan_chart_frame(result)
        outer = alt.Chart(fan).mark_area(color="#a6cee3", opacity=.55).encode(x=alt.X("month:Q", title="Months"), y="p5:Q", y2="p95:Q")
        inner = alt.Chart(fan).mark_area(color="#1f78b4", opacity=.35).encode(x="month:Q", y="p25:Q", y2="p75:Q")
        st.altair_chart(outer + inner + alt.Chart(fan).mark_line(color="black").encode(x="month:Q", y=alt.Y("median:Q", title="Dollar value")), use_container_width=True)
        comparison = []
        for name, weights in portfolios:
            r = cached_simulation(estimates["monthly_returns"], weights, objective, method, seed)
            comparison.append({"portfolio": name, "chance annualized return meets objective": r["probability_objective"], "chance value falls below $90 million": r["probability_below_90m"], "median ending value": r["median_ending_value"], "5th percentile": r["p5_ending_value"], "95th percentile": r["p95_ending_value"]})
        st.dataframe(pd.DataFrame(comparison), hide_index=True, use_container_width=True)
    with tabs[6]:
        results = cached_backtest(returns, cost); values = pd.concat([frame[["month", "value"]].assign(portfolio=name) for name, frame in results["histories"].items()])
        st.altair_chart(alt.Chart(values).mark_line().encode(x="month:T", y=alt.Y("value:Q", title="Dollar value"), color="portfolio:N"), use_container_width=True)
        weights = results["histories"]["Constrained portfolio"].melt(id_vars="month", value_vars=list(FUNDS), var_name="fund", value_name="weight")
        st.altair_chart(alt.Chart(weights).mark_area().encode(x="month:T", y=alt.Y("weight:Q", stack="normalize", axis=alt.Axis(format="%")), color="fund:N"), use_container_width=True); st.dataframe(results["summary"], hide_index=True, use_container_width=True)
    with tabs[7]: st.header("Recommendation")
if __name__ == "__main__": main()
