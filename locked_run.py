"""Locked Changed-Input run: VT expected return 2 points lower, everything else unchanged."""
import sys; sys.path.insert(0, ".")
from run_analysis import *  # same imports and defaults as the visible output
from simulation import simulate_portfolio

returns, _ = load_monthly_returns()
cpi, _, _ = load_cpi_as_known(DEFAULT_DECISION_DATE)
publication, _, _ = load_first_publication_date(cpi, DEFAULT_DECISION_DATE)
inflation = cpi_signal(cpi, DEFAULT_DECISION_DATE, publication)["inflation"]

def run(label, frame):
    est = estimate_from_monthly_returns(frame)
    mix = search_lowest_volatility(est, lambda w, r: check_portfolio(w, r, inflation))
    print(f"\n{label}: VT expected return {est['returns'][3]:.2%}, objective {inflation + .04:.2%}")
    if mix is None:
        print("  constrained portfolio: no mix meets the mandate")
    else:
        print("  constrained portfolio:", dict(zip(FUNDS, [round(w * 100) for w in mix["weights"]])),
              f"return {mix['expected_return']:.2%} volatility {mix['volatility']:.2%}")
    for name, w in [("Constrained (base mix)", BASE_MIX), ("60/40 benchmark", BENCHMARK_WEIGHTS), ("Equal weight", (.25,) * 4)]:
        s = simulate_portfolio(est["monthly_returns"], w, inflation + .04)
        print(f"  {name}: chance of objective {s['probability_objective']:.1%}, below $90M {s['probability_below_90m']:.1%}, median ${s['median_ending_value']/1e6:.1f}M")
    return mix

BASE_MIX = (0, .10, .30, .60)
base = run("BASE", returns)
changed = returns.copy(); changed["VT"] = changed["VT"] - 0.02 / 12
run("CHANGED (VT -2 points)", changed)
