from datetime import date
import pandas as pd
import pytest

from mandate import BENCHMARK_WEIGHTS, check_portfolio
from portfolio import estimate_from_monthly_prices, portfolio_metrics, search_lowest_volatility
import cpi_signal as cpi_module
from cpi_signal import cpi_signal, load_first_publication_date
from asof import TABLE, keep_latest_revisions, parse_table, remove_exact_duplicates, remove_matching
from stress import run_stress
from data import treasury_bill_proxy_return
from simulation import simulate_portfolio
from backtest import run_backtest


def test_meridian_known_answer_as_loaded():
    estimates = {"returns": (.035, .043, .050, .080), "volatilities": (.005, .070, .060, .160),
                 "correlation": ((1, .10, .05, 0), (.10, 1, .80, -.10), (.05, .80, 1, .25), (0, -.10, .25, 1))}
    candidate = search_lowest_volatility(estimates, lambda w, r: [{"pass": r >= .065 and w[0] + w[1] >= .03}])
    assert candidate["weights"] == pytest.approx((0, .20, .25, .55))
    assert candidate["expected_return"] == pytest.approx(.0651)
    assert candidate["volatility"] == pytest.approx(.0944, abs=.0001)


def test_lab_16_as_of_training_table_signals():
    rows = parse_table(TABLE)
    rows, _ = remove_matching(rows, lambda row: not row["Ticker"] or row["Ticker"] == "(blank)")
    rows, _ = remove_exact_duplicates(rows)
    rows, _ = remove_matching(rows, lambda row: row["Published on"] > date(2026, 3, 31))
    panel, _ = keep_latest_revisions(rows)
    by_ticker = {}
    for row in panel:
        by_ticker.setdefault(row["Ticker"], []).append(row)
    changes = {ticker: sorted(values, key=lambda row: row["Month measured"])[-1]["Index"] /
               sorted(values, key=lambda row: row["Month measured"])[-2]["Index"] - 1
               for ticker, values in by_ticker.items()}
    assert changes["AAA"] == pytest.approx(.0198, abs=.0001)
    assert changes["BBB"] == pytest.approx(-.0102, abs=.0001)
    assert changes["CCC"] == pytest.approx(.0091, abs=.0001)


def test_equal_weight_and_benchmark_verdicts():
    inflation = .025
    equal = check_portfolio((.25, .25, .25, .25), .06, inflation)
    benchmark = check_portfolio(BENCHMARK_WEIGHTS, .07, inflation)
    assert not all(rule["pass"] for rule in equal)
    assert all(rule["pass"] for rule in benchmark)
    assert any(rule["rule"] == "Return at least inflation + objective spread" and not rule["pass"] for rule in equal)


def test_cpi_signal_uses_latest_known_month_and_year_earlier_value():
    cpi = pd.DataFrame({"month": pd.to_datetime(["2025-08-01", "2026-08-01"]), "cpi": [300, 306]})
    result = cpi_signal(cpi, date(2026, 9, 30), date(2026, 9, 11))
    assert result["inflation"] == pytest.approx(.02)
    assert result["month"] == date(2026, 8, 1)
    assert result["publication_date"] == date(2026, 9, 11)


def test_first_publication_date_uses_and_caches_first_alfred_vintage(monkeypatch, tmp_path):
    cpi = pd.DataFrame({"month": pd.to_datetime(["2025-08-01", "2026-08-01"]), "cpi": [300, 306]})
    monkeypatch.setattr(cpi_module, "DATA_DIRECTORY", tmp_path)
    calls = []
    real_read_csv = cpi_module.pd.read_csv

    def fake_read_csv(location, *args, **kwargs):
        if str(location).startswith("https://"):
            calls.append(location)
            return pd.DataFrame({"observation_date": ["2026-08-01"], "CPIAUCSL": [306]})
        return real_read_csv(location, *args, **kwargs)

    monkeypatch.setattr(cpi_module.pd, "read_csv", fake_read_csv)
    publication, path, downloaded = load_first_publication_date(cpi, date(2026, 9, 30))
    assert publication == date(2026, 8, 31)
    assert downloaded
    assert path.exists()
    publication, _, downloaded = load_first_publication_date(cpi, date(2026, 9, 30))
    assert publication == date(2026, 8, 31)
    assert not downloaded
    assert len(calls) == 1


def test_stress_costs_use_benchmark_turnover_and_cases_are_independent():
    prices = pd.read_csv("prices.csv")
    rows = run_stress(prices, .03, (.50, 0, 0, .50), .04)
    cases = [row["case"] for row in rows]
    assert "Last 36 monthly returns" in cases
    assert not any("Last 36 monthly returns;" in case for case in cases)
    assert "Reserve minimum 10%" in cases
    assert "60% cap off" in cases
    assert not any("; 60% cap" in case for case in cases)
    cost_row = next(row for row in rows if row["case"] == "Transaction cost 10 basis points")
    expected_turnover = sum(abs(weight - benchmark_weight) for weight, benchmark_weight in zip(cost_row["weights"], BENCHMARK_WEIGHTS)) / 2
    expected_trading_cost_dollars = expected_turnover * .001 * 100_000_000
    assert cost_row["turnover"] == pytest.approx(expected_turnover)
    assert cost_row["trading_cost_dollars"] == pytest.approx(expected_trading_cost_dollars)
    gross_return, _ = portfolio_metrics(cost_row["weights"], estimate_from_monthly_prices(prices))
    assert cost_row["expected_return_after_cost"] == pytest.approx(gross_return - expected_turnover * .0010)


def test_treasury_bill_proxy_math():
    assert treasury_bill_proxy_return(5.28) == pytest.approx(5.28 / 12 / 100)


def test_monte_carlo_repeats_with_same_seed():
    returns = pd.DataFrame({"SGOV": [.001, .002, .003], "IEF": [.01, -.01, .005],
                            "USIG": [.004, -.002, .006], "VT": [.02, -.01, .03]})
    first = simulate_portfolio(returns, (.25, .25, .25, .25), .05, seed=99, paths=100)
    second = simulate_portfolio(returns, (.25, .25, .25, .25), .05, seed=99, paths=100)
    assert first["values"] == pytest.approx(second["values"])


def test_backtest_choice_does_not_use_later_returns():
    months = pd.date_range("2010-01-01", periods=39, freq="MS")
    base = pd.DataFrame({"month": months, "SGOV": .001, "IEF": .002, "USIG": .003, "VT": .004})
    dates = [(month + pd.offsets.MonthEnd(0)).date() for month in months[35:-1]]
    vintages = pd.DataFrame({"decision_date": dates, "inflation": [.01] * len(dates)})
    original = run_backtest(base, cpi_vintages=vintages)["histories"]["Constrained portfolio"].iloc[0][["SGOV", "IEF", "USIG", "VT"]]
    changed = base.copy(); changed.loc[36:, ["SGOV", "IEF", "USIG", "VT"]] = 9.0
    altered = run_backtest(changed, cpi_vintages=vintages)["histories"]["Constrained portfolio"].iloc[0][["SGOV", "IEF", "USIG", "VT"]]
    assert original.to_numpy() == pytest.approx(altered.to_numpy())
