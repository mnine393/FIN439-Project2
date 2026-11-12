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
from recommendation import ACTION, ALLOCATION_RANGE, COMMITTEE_ASK, CONDITIONS, TRIGGERS
from simulation import fan_chart_frame, simulate_portfolio
from stress import run_stress

AI_STATEMENT = "AI use: built with OpenAI Codex (GPT-5.6-Terra) for the code and Claude for planning and checking; the analysis and the decision are mine."
ADVICE_STATEMENT = "Education, not investment advice."
COLORS = {"Constrained portfolio": "#22c1b6", "60/40 benchmark": "#d9a441", "Equal weight": "#9ca3af"}
def money(x, compact=False): return "not applicable" if pd.isna(x) else (f"${x/1e6:,.1f} million" if compact else f"${x:,.0f}")
def rate(x): return "not applicable" if pd.isna(x) else f"{x:.2%}"
def weights_text(w): return " | ".join(f"{f}: {rate(x)} ({money(x * PORTFOLIO_SIZE_DOLLARS)})" for f, x in zip(FUNDS, w))
def verdict_frame(r): return pd.DataFrame({"Rule": [x["rule"] for x in r], "Verdict": ["Pass" if x["pass"] else "Fail" for x in r]})
def card(label, value, detail="", color=""):
    st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value" style="color:{color}">{value}</div><div class="metric-detail">{detail}</div></div>', unsafe_allow_html=True)
def clean_table(frame):
    shown = frame.copy()
    for c in shown:
        if any(x in c.lower() for x in ("return", "volatility", "drop", "turnover", "probability", "weight", "change")): shown[c] = shown[c].map(rate)
        elif any(x in c.lower() for x in ("value", "dollars")): shown[c] = shown[c].map(money)
    return shown.fillna("not applicable")
def chart_style(chart, title):
    return chart.properties(title=alt.TitleParams(title, color="#e8f0f5", font="sans-serif", fontSize=16)).configure_view(strokeOpacity=0).configure_axis(labelColor="#cbd5e1", titleColor="#e8f0f5", gridColor="#294052", labelFont="sans-serif", titleFont="sans-serif").configure_legend(labelColor="#e8f0f5", titleColor="#e8f0f5")
@st.cache_data(show_spinner=False)
def cached_frontier(returns, inflation, reserve, cap, spread):
    return evaluate_frontier(estimate_from_monthly_returns(returns), lambda w, r: check_portfolio(w, r, inflation, reserve_minimum=reserve, use_maximum_fund_weight=cap, objective_spread=spread))
@st.cache_data(show_spinner=False)
def cached_simulation(returns, weights, objective, method, seed): return simulate_portfolio(returns, weights, objective, method=method, seed=seed)
@st.cache_data(show_spinner=False)
def cached_backtest(returns, cost): return run_backtest(returns, trading_cost_basis_points=cost)

def main():
    st.set_page_config(page_title="Endowment Command Center", layout="wide")
    st.markdown("<style>.metric-card{border:1px solid #294052;border-radius:10px;padding:16px;min-height:128px;background:#0b1a28}.metric-label{color:#a9bac8;font-size:.85rem;margin-bottom:8px}.metric-value{font-size:1.55rem;font-weight:650;line-height:1.15}.metric-detail{color:#cbd5e1;font-size:.82rem;margin-top:10px}</style>", unsafe_allow_html=True)
    st.write(AI_STATEMENT); st.write(ADVICE_STATEMENT); st.title("Endowment Command Center")
    with st.sidebar:
        st.header("Decision")
        decision_date = st.date_input("Decision date", DEFAULT_DECISION_DATE, help="Limits inflation information to what was known on this date.")
        window = st.selectbox("Estimate window", ["all history", "last 60 months", "last 36 months"], help="Monthly return history used to estimate return and risk.")
        st.header("Mandate limits")
        cap = st.toggle("Use the 60% fund cap", value=True, help="Limits any one fund to 60% of the portfolio.")
        reserve = st.number_input("Minimum SGOV + IEF reserve (percent)", 0., 100., 3., 1., help="Minimum combined allocation to the cash and Treasury funds.") / 100
        spread = st.number_input("Objective spread over inflation (percent)", -100., 100., 4., 1., help="Required annual return above Consumer Price Index inflation.") / 100
        st.header("Stress and stop rule")
        stop = st.number_input("Stop threshold for a weight change (percent)", 0., 100., 20., 1., help="A stress case stops the process when its largest allocation change exceeds this amount.") / 100
        cost = st.number_input("Backtest trading cost (basis points)", 0., 100., 10., 1., help="Cost charged on each month's calculated trading turnover.")
        st.header("Simulation")
        refresh = st.button("Refresh market data", help="Downloads current market data; otherwise saved local data is used.")
    try:
        returns, market_download = load_monthly_returns(refresh); cpi, saved, cpi_download = load_cpi_as_known(decision_date)
        publication, publication_saved, publication_download = load_first_publication_date(cpi, decision_date); signal = cpi_signal(cpi, decision_date, publication)
    except Exception as error: st.error(f"Required offline data is unavailable: {error}"); return
    estimates = estimate_from_monthly_returns(returns, window); inflation = signal["inflation"]; objective = inflation + spread
    checker = lambda w, r: check_portfolio(w, r, inflation, reserve_minimum=reserve, use_maximum_fund_weight=cap, objective_spread=spread)
    constrained = search_lowest_volatility(estimates, checker); equal = (.25,) * 4
    portfolios = [("Equal weight", equal), ("60/40 benchmark", BENCHMARK_WEIGHTS)] + ([("Constrained portfolio", constrained["weights"])] if constrained else [])
    stress_rows = run_stress(returns, inflation, constrained["weights"], spread) if constrained else []
    triggers = [] if not constrained else [row["case"] for row in stress_rows if row["weights"] is None or row["largest_weight_change"] > stop]
    frontier = cached_frontier(returns.loc[:, list(FUNDS)], inflation, reserve, cap, spread)
    tabs = st.tabs(["Committee summary", "Mandate", "Signal", "Portfolios", "Stress", "Frontier", "Will the money last?", "Would it have worked?"])
    with tabs[0]:
        st.header("Committee summary")
        cols = st.columns(4)
        with cols[0]: card("Portfolio size", money(PORTFOLIO_SIZE_DOLLARS), "Foundation assets")
        with cols[1]: card("Consumer Price Index year-over-year", rate(inflation), f"Month: {signal['month']}; first published: {signal['publication_date']}")
        with cols[2]: card("Objective", rate(objective), f"Consumer Price Index plus {rate(spread)}")
        with cols[3]:
            if not constrained: card("Stop condition", "Stop condition triggered", "No mix meets the mandate", "#f87171")
            elif triggers: card("Stop condition", "Stop condition triggered", "; ".join(triggers), "#f87171")
            else: card("Stop condition", "Stable", "No stress case triggered the stop rule", "#4ade80")
        st.header("The evidence"); evidence = st.columns(3); meets = int(frontier["meets_mandate"].sum())
        with evidence[0]: card("Frontier", f"{meets:,} of {len(frontier):,}", "Mixes that meet every mandate rule")
        with evidence[1]:
            lines=[]
            for name in ("Constrained portfolio", "60/40 benchmark"):
                if name in dict(portfolios):
                    r=cached_simulation(estimates["monthly_returns"], dict(portfolios)[name], objective, "Historical bootstrap", 439); lines.append(f"{name}: objective {rate(r['probability_objective'])}; below $90 million {rate(r['probability_below_90m'])}")
            card("Will the money last", "Seven-year simulation", "<br>".join(lines))
        with evidence[2]:
            result=cached_backtest(returns,cost)["summary"].set_index("portfolio"); lines=[f"{n}: {money(result.loc[n,'ending_dollar_value'])}; worst drop {rate(result.loc[n,'worst_peak_to_trough_drop'])}" for n in ("Constrained portfolio","60/40 benchmark","Equal weight") if n in result.index]; card("Would it have worked", "Expanding-window backtest", "<br>".join(lines))
        st.header("Recommendation"); st.warning("Recommendation fields are not yet decided.")
        st.dataframe(pd.DataFrame({"Item":["Action","Allocation range","Conditions","Triggers","Committee ask"],"Committee decision":[ACTION,ALLOCATION_RANGE,CONDITIONS,"; ".join(TRIGGERS),COMMITTEE_ASK]}),hide_index=True,width="stretch")
    with tabs[1]:
        st.header("Mandate"); st.write(f"Objective: at least Consumer Price Index inflation plus {rate(spread)} ({rate(objective)}) each year over seven years."); st.write(f"Portfolio size: {money(PORTFOLIO_SIZE_DOLLARS)}; quarterly payout: {money(QUARTERLY_PAYOUT_DOLLARS)}. The 3% reserve rule equals four quarterly payouts divided by portfolio size."); st.dataframe(verdict_frame(checker(equal,portfolio_metrics(equal,estimates)[0])),hide_index=True,width="stretch")
    with tabs[2]:
        st.header("Inflation signal"); st.write(f"Consumer Price Index year-over-year: {rate(inflation)}; latest known month: {signal['month']}; first published: {signal['publication_date']}."); st.caption(f"Market returns: {'Downloaded for this run.' if market_download else 'Used saved copy.'} Consumer Price Index: {'Downloaded for this run.' if cpi_download else 'Used saved copy.'}"); st.caption(f"Publication-date source: {publication_saved}. {'Downloaded for this run.' if publication_download else 'Used saved copy.'}"); st.markdown(Path("docs/data-card.md").read_text(encoding="utf-8")); st.markdown(Path("docs/data-card-prices.md").read_text(encoding="utf-8"))
    with tabs[3]:
        st.header("Portfolios")
        for col,(name,w) in zip(st.columns(3),portfolios):
            expected,volatility=portfolio_metrics(w,estimates)
            with col: card(name,rate(expected),f"Expected annual return; volatility {rate(volatility)}",COLORS[name]); st.caption(weights_text(w)); st.dataframe(verdict_frame(checker(w,expected)),hide_index=True,width="stretch")
        if not constrained: st.error("No mix meets the mandate.")
    with tabs[4]:
        st.header("Stress")
        if not constrained: st.error("Stop condition triggered: no mix meets the mandate in the base case.")
        else:
            table=pd.DataFrame([{**row,"weights":"No mix meets the mandate" if row["weights"] is None else weights_text(row["weights"])} for row in stress_rows]); st.dataframe(clean_table(table),hide_index=True,width="stretch"); st.error("Stop condition triggered: "+"; ".join(triggers)) if triggers else st.success("Stable: no stress case triggered the stop rule.")
    with tabs[5]:
        st.header("Frontier")
        base=alt.Chart(frontier).mark_circle(size=45).encode(x=alt.X("volatility:Q",title="Annual volatility (%)",axis=alt.Axis(format="%")),y=alt.Y("expected_return:Q",title="Expected annual return (%)",axis=alt.Axis(format="%")),color=alt.condition("datum.meets_mandate",alt.value("#22c1b6"),alt.value("#596675")),opacity=alt.condition("datum.meets_mandate",alt.value(.9),alt.value(.25)),tooltip=[alt.Tooltip(f"{f}:Q",format=".2%",title=f) for f in FUNDS])
        objective_line=alt.Chart(pd.DataFrame({"objective":[objective]})).mark_rule(color="#f87171").encode(y="objective:Q")
        labels=pd.DataFrame([{"name":n,"volatility":portfolio_metrics(w,estimates)[1],"expected_return":portfolio_metrics(w,estimates)[0]} for n,w in portfolios]); points=alt.Chart(labels).mark_point(shape="diamond",size=130).encode(x="volatility:Q",y="expected_return:Q",color=alt.Color("name:N",scale=alt.Scale(domain=list(COLORS),range=list(COLORS.values())),legend=None),tooltip=["name:N",alt.Tooltip("volatility:Q",format=".2%"),alt.Tooltip("expected_return:Q",format=".2%")])
        st.altair_chart(chart_style(base+objective_line+points,"Long-only portfolio mixes"),width="stretch"); st.caption("This chart shows each tested mix by expected annual return and annual volatility; teal mixes meet every mandate rule.")
    with tabs[6]:
        st.header("Will the money last?"); method=st.selectbox("Simulation method",["Historical bootstrap","Normal distribution"],help="Historical bootstrap reuses observed months; normal distribution draws from a fitted distribution."); seed=int(st.number_input("Random seed",0,2147483647,439,1,help="Keeps the random simulation repeatable.")); selected=st.selectbox("Portfolio for fan chart",[n for n,_ in portfolios],help="Selects the portfolio shown in the chart.")
        r=cached_simulation(estimates["monthly_returns"],dict(portfolios)[selected],objective,method,seed); fan=fan_chart_frame(r); outer=alt.Chart(fan).mark_area(color="#376b83",opacity=.55).encode(x=alt.X("month:Q",title="Months"),y=alt.Y("p5:Q",title="Portfolio value ($ millions)",axis=alt.Axis(format="~s")),y2="p95:Q"); inner=alt.Chart(fan).mark_area(color=COLORS[selected],opacity=.35).encode(x="month:Q",y="p25:Q",y2="p75:Q"); median=alt.Chart(fan).mark_line(color=COLORS[selected]).encode(x="month:Q",y="median:Q",tooltip=["month:Q",alt.Tooltip("median:Q",format="$,.0f")]); st.altair_chart(chart_style(outer+inner+median,f"{selected} simulated values"),width="stretch"); st.caption("This chart shows the middle and wider ranges of simulated seven-year portfolio values in dollars.")
        comparison=[]
        for n,w in portfolios:
            x=cached_simulation(estimates["monthly_returns"],w,objective,method,seed); comparison.append({"Portfolio":n,"Chance of meeting objective":rate(x["probability_objective"]),"Chance below $90 million":rate(x["probability_below_90m"]),"Median ending value":money(x["median_ending_value"])})
        st.dataframe(pd.DataFrame(comparison),hide_index=True,width="stretch")
    with tabs[7]:
        st.header("Would it have worked?"); results=cached_backtest(returns,cost); values=pd.concat([frame[["month","value"]].assign(portfolio=n) for n,frame in results["histories"].items()]); value_chart=alt.Chart(values).mark_line().encode(x=alt.X("month:T",title="Month"),y=alt.Y("value:Q",title="Portfolio value ($ millions)",axis=alt.Axis(format="~s")),color=alt.Color("portfolio:N",scale=alt.Scale(domain=list(COLORS),range=list(COLORS.values())),title="Portfolio"),tooltip=["portfolio:N","month:T",alt.Tooltip("value:Q",format="$,.0f")]); st.altair_chart(chart_style(value_chart,"Historical portfolio values"),width="stretch"); st.caption("This chart shows the historical dollar value of each strategy after payouts and trading costs.")
        weights=results["histories"]["Constrained portfolio"].melt(id_vars="month",value_vars=list(FUNDS),var_name="fund",value_name="weight"); weight_chart=alt.Chart(weights).mark_area().encode(x=alt.X("month:T",title="Month"),y=alt.Y("weight:Q",stack="normalize",title="Portfolio weight (%)",axis=alt.Axis(format="%")),color=alt.Color("fund:N",title="Fund"),tooltip=["fund:N","month:T",alt.Tooltip("weight:Q",format=".2%")]); st.altair_chart(chart_style(weight_chart,"Constrained portfolio allocations"),width="stretch"); st.caption("This chart shows how the constrained portfolio’s target fund allocations changed through time."); st.dataframe(clean_table(results["summary"]),hide_index=True,width="stretch")

if __name__ == "__main__": main()
