"""Offline checks for Build G forecasting and portfolio analysis."""
import numpy as np
import pandas as pd

import analyze
import forecast
import run_analysis
import server
from analyze import analyze_portfolio, risk_profile
from universe import Fund


FUNDS = (Fund("AAA", role="stocks"), Fund("BBB", role="government bonds"), Fund("CCC", role="cash"), Fund("DDD", role="commodities"), Fund("VT", role="stocks"))

def synthetic_returns(months=96):
    rng = np.random.default_rng(10)
    index = pd.date_range("2010-01-31", periods=months, freq="ME")
    return pd.DataFrame(rng.normal(.005, .03, size=(months, 5)), index=index, columns=[f.ticker for f in FUNDS])

def fake_fred(series):
    return pd.Series([2., 3.], index=pd.to_datetime(["2015-01-31", "2020-01-31"]), name=series)

def test_block_bootstrap_keeps_consecutive_runs_together():
    draws = forecast._block_draws(100, 24, 12, np.random.default_rng(439))[0]
    assert np.all((np.diff(draws[:12]) % 100) == 1)
    assert np.all((np.diff(draws[12:]) % 100) == 1)


def test_fetch_fred_series_converts_date_series_to_month_end(tmp_path, monkeypatch):
    source = tmp_path / "fred"
    source.mkdir()
    (source / "TEST.csv").write_text("date,value\n2020-01-15,2.5\n", encoding="utf-8")
    monkeypatch.setattr(forecast, "FRED_DIRECTORY", source)
    forecast._load_fred_series.cache_clear()
    result = forecast.fetch_fred_series("TEST")
    assert result.index[0] == pd.Timestamp("2020-01-31")


def test_forecast_rejects_undated_returns():
    returns = synthetic_returns().reset_index(drop=True)
    with np.testing.assert_raises_regex(ValueError, "Forecast returns need month dates; got an undated table."):
        forecast.forecast_portfolio([1, 0, 0, 0, 0], returns, FUNDS, start_value=1, months=12)

def test_improved_mean_matches_blended_assumption(monkeypatch):
    monkeypatch.setattr(forecast, "fetch_fred_series", fake_fred)
    returns = synthetic_returns()
    output = forecast.forecast_portfolio([1, 0, 0, 0, 0], returns, FUNDS, start_value=1, months=12,
                                         paths=5000, parameter_uncertainty=False, keep_ending_values=True)
    target = output["assumptions"]["AAA"]["blended"]
    actual = np.mean(output["ending_values"] - 1)
    assert abs(actual - target) < .015

def test_assumptions_are_point_in_time(monkeypatch):
    values = {"TB3MS": [2., 2., 99.], "GS10": [3., 3., 99.], "BAA": [4., 4., 99.]}
    def local(series): return pd.Series(values[series], index=pd.to_datetime(["2019-01-31", "2020-01-31", "2021-01-31"]))
    monkeypatch.setattr(forecast, "fetch_fred_series", local)
    first = forecast.capital_market_assumptions(FUNDS, synthetic_returns(), "2020-06-30")
    values["TB3MS"][-1] = 1.
    second = forecast.capital_market_assumptions(FUNDS, synthetic_returns(), "2020-06-30")
    assert first == second

def test_shrunk_covariance_is_positive_definite():
    matrix, intensity = forecast.shrunk_covariance(synthetic_returns())
    assert np.allclose(matrix, matrix.T)
    assert np.all(np.linalg.eigvalsh(matrix) > 0)
    assert 0 <= intensity <= 1

def test_crisis_proxy_is_labeled(monkeypatch):
    monkeypatch.setattr(forecast, "fetch_fred_series", fake_fred)
    frame = synthetic_returns(180)
    frame.index = pd.date_range("2008-01-31", periods=180, freq="ME")
    missing = (Fund("MISSING", role="stocks"), Fund("VT", role="stocks"))
    output = forecast.crisis_scenarios([.5, .5], frame[["VT"]], missing)
    assert output[0]["sources"]["MISSING"] == "proxy"


def test_crisis_uses_vt_proxy_before_stock_history_starts():
    index = pd.date_range("2008-01-31", "2016-12-31", freq="ME")
    frame = pd.DataFrame({"AAA": np.nan, "BBB": np.nan, "VT": .01}, index=index)
    frame.loc[frame.index >= "2015-01-31", ["AAA", "BBB"]] = .02
    funds = (Fund("AAA", role="stocks"), Fund("BBB", role="individual stock"))
    result = forecast.crisis_scenarios([.5, .5], frame, funds)[0]
    assert result["sources"] == {"AAA": "proxy", "BBB": "proxy"}
    assert result["portfolio_return"] is not None


def test_crisis_notes_missing_market_reference():
    index = pd.date_range("2015-01-31", "2016-12-31", freq="ME")
    frame = pd.DataFrame({"AAA": .02, "BBB": .01}, index=index)
    funds = (Fund("AAA", role="stocks"), Fund("BBB", role="individual stock"))
    result = forecast.crisis_scenarios([.5, .5], frame, funds)[0]
    assert result["note"] == "No market data for this period."
    assert result["portfolio_return"] is None

def test_analyze_has_all_main_sections(monkeypatch):
    monkeypatch.setattr(forecast, "fetch_fred_series", fake_fred)
    monkeypatch.setattr(analyze, "fetch_fred_series", fake_fred)
    result = analyze_portfolio({fund.ticker: 100 for fund in FUNDS}, FUNDS, synthetic_returns(), horizon_years=1)
    for key in ("weights", "history", "risk_contribution", "correlation", "drawdown_series", "growth_of_10000", "risk_score", "concentration", "fees", "forecast", "crisis_scenarios", "flags"):
        assert key in result


def test_ending_values_are_opt_in_and_goal_is_reported(monkeypatch):
    monkeypatch.setattr(forecast, "fetch_fred_series", fake_fred)
    result = forecast.forecast_portfolio([1, 0, 0, 0, 0], synthetic_returns(), FUNDS,
                                         start_value=1, months=12, paths=100, goal=1)
    assert "ending_values" not in result
    assert 0 <= result["chance_of_goal"] <= 1


def test_simple_forecast_does_not_load_yields(monkeypatch):
    def fail_if_called(series):
        raise AssertionError(f"simple forecast requested {series}")
    monkeypatch.setattr(forecast, "fetch_fred_series", fail_if_called)
    result = forecast.forecast_portfolio([1, 0, 0, 0, 0], synthetic_returns(), FUNDS,
                                         start_value=1, months=12, method="simple", paths=100)
    assert result["expected_annual_return"] == result["assumptions"]["AAA"]["history_mean"]


def test_risk_contributions_add_to_one_hundred_percent(monkeypatch):
    monkeypatch.setattr(forecast, "fetch_fred_series", fake_fred)
    monkeypatch.setattr(analyze, "fetch_fred_series", fake_fred)
    result = analyze_portfolio({fund.ticker: 100 for fund in FUNDS}, FUNDS, synthetic_returns(), horizon_years=1)
    assert np.isclose(sum(result["risk_contribution"].values()), 100)
    assert all(isinstance(value, float) for row in result["correlation"]["matrix"] for value in row)


def test_forecast_at_date_is_unchanged_by_later_return(monkeypatch):
    returns = synthetic_returns()
    as_of = returns.index[60]
    first = forecast.forecast_portfolio([1, 0, 0, 0, 0], returns, FUNDS, start_value=1,
                                        months=12, method="simple", paths=200, seed=7, as_of=as_of)
    changed = returns.copy()
    changed.loc[changed.index > as_of, "AAA"] = 0.99
    second = forecast.forecast_portfolio([1, 0, 0, 0, 0], changed, FUNDS, start_value=1,
                                         months=12, method="simple", paths=200, seed=7, as_of=as_of)
    assert first == second


def test_default_plan_responses_report_decision_date_yields(monkeypatch):
    """Both default plan responses retain monthly dates through forecasting."""
    def dated_yields(series):
        return pd.Series([4.0], index=pd.DatetimeIndex(["2026-09-30"]), name=series)

    monkeypatch.setattr(forecast, "fetch_fred_series", dated_yields)
    server.institution_cached.cache_clear()
    server.personal_cached.cache_clear()
    institution = server.institution_cached()
    personal = server.personal_cached('{"savings":40000,"monthly_contribution":1200,"goal":1000000,"years":30,"tolerated_drop":0.4,"monthly_expenses":3000,"reserve_months":6}')
    expected = {"TB3MS": "2026-09-30", "GS10": "2026-09-30", "BAA": "2026-09-30"}
    assert institution["improved_forecast"]["yield_dates"] == expected
    assert personal["improved_forecast"]["yield_dates"] == expected
    server.institution_cached.cache_clear()
    server.personal_cached.cache_clear()


def test_run_analysis_forecast_section_uses_dated_returns_and_has_no_1970_date(tmp_path, monkeypatch):
    """The non-web report sends dated returns to its forecasts and calibration."""
    returns = pd.DataFrame({"month": pd.date_range("2022-01-31", periods=4, freq="ME"),
                            "SGOV": [.01] * 4, "IEF": [.01] * 4,
                            "USIG": [.01] * 4, "VT": [.01] * 4})
    estimates = {"returns": (.12,) * 4, "volatilities": (.01,) * 4,
                 "correlation": np.eye(4), "monthly_returns": returns[list(("SGOV", "IEF", "USIG", "VT"))]}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(run_analysis, "load_monthly_returns", lambda: (returns, False))
    monkeypatch.setattr(run_analysis, "load_cpi_as_known", lambda _: (pd.DataFrame(), "saved", False))
    monkeypatch.setattr(run_analysis, "load_first_publication_date", lambda *_: ("2026-09-30", "saved", False))
    monkeypatch.setattr(run_analysis, "cpi_signal", lambda *_: {"inflation": .03, "month": "2026-09-30"})
    monkeypatch.setattr(run_analysis, "estimate_from_monthly_returns", lambda _: estimates)
    monkeypatch.setattr(run_analysis, "search_lowest_volatility", lambda *_: None)
    monkeypatch.setattr(run_analysis, "evaluate_frontier", lambda *_: pd.DataFrame({"meets_mandate": [True]}))
    monkeypatch.setattr(run_analysis, "simulate_portfolio", lambda *_args, **_kwargs: {"probability_objective": .5, "probability_below_90m": .1, "median_ending_value": 1, "p5_ending_value": 1, "p95_ending_value": 1})
    monkeypatch.setattr(run_analysis, "run_backtest", lambda *_: {"summary": pd.DataFrame()})
    monkeypatch.setattr(run_analysis, "run_stress", lambda *_: [])
    monkeypatch.setattr(run_analysis, "stop_summary", lambda *_: {"triggered": False, "threshold": .2, "triggered_cases": []})
    monkeypatch.setattr(run_analysis, "committee_report", lambda *_: {"members": [], "outcome": "No vote"})
    monkeypatch.setattr(run_analysis, "plan", lambda *_: {"portfolios": [], "emergency_reserve": {"invested_starting_amount": 22_000}, "contribution_for_80_percent": None})

    def dated_forecast(_weights, history, *_args, **_kwargs):
        assert "month" in history
        return {"percentiles": {"84": {"p10": 1, "p50": 1, "p90": 1}}, "method": "test",
                "expected_annual_return": .05, "chance_of_goal": .5,
                "yield_dates": {"TB3MS": "2026-09-30", "GS10": "2026-09-30", "BAA": "2026-09-30"}}

    def dated_calibration(_weights, history, *_args, **_kwargs):
        assert "month" in history
        return {"methods": {"improved": {"12": {"number_of_forecasts": 1, "inside_10_90": .8,
                                                    "below_10": .1, "above_90": .1, "pinball_loss": .01}}}}

    monkeypatch.setattr(run_analysis, "forecast_portfolio", dated_forecast)
    monkeypatch.setattr(run_analysis, "calibration_test", dated_calibration)
    run_analysis.main()
    report = (tmp_path / "output" / "visible_output.md").read_text(encoding="utf-8")
    assert "TB3MS: 2026-09-30" in report
    assert "1970" not in report
    assert "$5,500" in run_analysis.show_weights((.25,) * 4, 22_000)

def test_risk_profile_bounds():
    assert risk_profile({"time_horizon": 5, "reaction": 5, "income_stability": 5, "experience": 5, "priority": 5})["score"] == 10
