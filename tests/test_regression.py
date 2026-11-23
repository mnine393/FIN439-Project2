"""Pinned Meridian figures reviewed by hand before Compass was introduced."""
import pytest
from cpi_signal import DEFAULT_DECISION_DATE, cpi_signal, load_cpi_as_known, load_first_publication_date
from data import load_monthly_returns
from mandate import BENCHMARK_WEIGHTS, check_portfolio
from portfolio import estimate_from_monthly_returns, portfolio_metrics, search_lowest_volatility
from frontier import evaluate_frontier
from simulation import simulate_portfolio
from backtest import run_backtest

def test_meridian_reviewed_results_are_unchanged():
    returns, _ = load_monthly_returns(); cpi, _, _ = load_cpi_as_known(DEFAULT_DECISION_DATE)
    publication, _, _ = load_first_publication_date(cpi, DEFAULT_DECISION_DATE)
    inflation = cpi_signal(cpi, DEFAULT_DECISION_DATE, publication)["inflation"]
    estimates = estimate_from_monthly_returns(returns)
    chosen = search_lowest_volatility(estimates, lambda w, r: check_portfolio(w, r, inflation))
    assert inflation == pytest.approx(.0335, abs=.00005)
    assert portfolio_metrics((.25,)*4, estimates) == pytest.approx((.0447, .0580), abs=.0001)
    assert portfolio_metrics(BENCHMARK_WEIGHTS, estimates) == pytest.approx((.0702, .1029), abs=.0001)
    assert chosen["weights"] == pytest.approx((0, .10, .30, .60))
    assert (chosen["expected_return"], chosen["volatility"]) == pytest.approx((.0736, .1123), abs=.0001)
    frontier = evaluate_frontier(estimates, lambda w, r: check_portfolio(w, r, inflation))
    assert (len(frontier), frontier.meets_mandate.sum()) == (1771, 2)
    expected = [(chosen["weights"], .4723, .4000, 134_131_071), (BENCHMARK_WEIGHTS, .4427, .3726, 131_334_489), ((.25,)*4, .0967, .2622, 110_895_947)]
    for weights, chance, below, median in expected:
        result = simulate_portfolio(estimates["monthly_returns"], weights, inflation+.04)
        assert result["probability_objective"] == pytest.approx(chance, abs=.0001)
        assert result["probability_below_90m"] == pytest.approx(below, abs=.0001)
        assert result["median_ending_value"] == pytest.approx(median, abs=1)
    table = run_backtest(returns)["summary"].set_index("portfolio")
    assert table.loc["Constrained portfolio", "ending_dollar_value"] == pytest.approx(134_296_207, abs=1)
    assert table.loc["60/40 benchmark", "ending_dollar_value"] == pytest.approx(200_614_136, abs=1)
    assert table.loc["Equal weight", "ending_dollar_value"] == pytest.approx(126_112_544, abs=1)
