"""Offline regression coverage for Build D custom-universe fixes."""

from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import data
import numpy as np
import portfolio
import server
from mandate import Mandate
from universe import Fund, benchmark_weights


def test_short_cash_history_uses_saved_treasury_bill_proxy(monkeypatch):
    months = pd.date_range("2008-06-01", "2021-01-01", freq="MS")

    def prices(fund, refresh=False):
        available = months if fund.ticker != "CASH" else months[months >= "2020-07-01"]
        values = pd.Series(range(100, 100 + len(available)), index=available, dtype=float)
        return values, {"name": fund.ticker, "first_month": available[0].date().isoformat(),
                        "last_month": available[-1].date().isoformat(), "downloaded_at": None}

    proxy = pd.DataFrame({"month": months[1:], "SGOV": .001, "IEF": .002,
                          "USIG": .003, "VT": .004, "sgov_source": "Treasury bill proxy"})
    monkeypatch.setattr(data, "load_fund_prices", prices)
    monkeypatch.setattr(data, "load_monthly_returns", lambda: (proxy, False))
    returns, _ = data.load_universe_returns((Fund("CASH", role="cash"), Fund("BOND", role="government bonds")),
                                             decision_date=date(2021, 2, 1))
    assert returns["month"].iloc[0] == pd.Timestamp("2008-07-01")
    assert returns.attrs == {}
    assert returns.loc[0, "CASH"] == .001
    assert returns.loc[0, "cash_source"] == "Treasury bill proxy"


def test_custom_optimizer_plan_has_personal_result_fields(monkeypatch):
    tickers = ("SGOV", "IEF", "AAPL", "AXP", "KO", "GOOGL", "BAC", "CVX", "OXY", "MCO", "GOOG", "KHC")
    months = pd.date_range("2018-01-01", periods=72, freq="MS")
    returns = pd.DataFrame({"month": months, **{ticker: .003 if ticker in {"SGOV", "IEF"} else .01
                                                 for ticker in tickers}})
    funds = [{"ticker": ticker, "role": "cash" if ticker == "SGOV" else "government bonds" if ticker == "IEF"
              else "individual stock", "reserve_eligible": ticker in {"SGOV", "IEF"}} for ticker in tickers]
    records = [{**fund, "name": fund["ticker"], "first_month": "2018-01-01", "last_month": "2023-12-01",
                "downloaded_at": None, "instrument_type": "ETF"} for fund in funds]
    weights = (.05, .55) + (.04,) * 10
    monkeypatch.setattr(server, "load_universe_returns", lambda *args, **kwargs: (returns, records))
    monkeypatch.setattr(server, "load_cpi_as_known", lambda _: (pd.DataFrame(), None, None))
    monkeypatch.setattr(server, "load_first_publication_date", lambda *args: (date(2026, 9, 1), None, None))
    monkeypatch.setattr(server, "cpi_signal", lambda *args: {"inflation": .02, "month": date(2026, 8, 1)})
    monkeypatch.setattr(server, "search_portfolio", lambda *args, **kwargs: {
        "weights": weights, "expected_return": .08, "volatility": .10, "method": "optimizer"})
    monkeypatch.setattr(server, "_screen_cached", lambda ticker, as_of: {"ticker": ticker, "buffett_score": "3 of 3",
                                                                            "burry_score": "2 of 2"})
    response = TestClient(server.app).post("/api/personal/plan", json={
        "savings": 100_000, "monthly_contribution": 0, "goal": 100_000, "years": 1,
        "tolerated_drop": .40, "monthly_expenses": 0, "reserve_months": 0, "universe": funds,
        "max_single_stock_weight": .10, "max_individual_stocks_total": .40, "min_holdings": 5})
    assert response.status_code == 200
    payload = response.json()
    assert payload["contribution_for_80_percent"] is not None
    assert payload["fan_chart"]
    assert payload["backtest"]["monthly_values"]
    assert payload["backtest"]["plan_weights"]
    assert payload["backtest"]["summary"]


def test_twelve_holding_universe_uses_and_reports_the_optimizer(monkeypatch):
    tickers = ("SGOV", "IEF", "AAPL", "AXP", "KO", "GOOGL", "BAC", "CVX", "OXY", "MCO", "GOOG", "KHC")
    funds = tuple(Fund(ticker, role="cash" if ticker == "SGOV" else "government bonds" if ticker == "IEF"
                       else "individual stock") for ticker in tickers)
    estimates = {"returns": (.08,) * len(funds), "volatilities": (.15,) * len(funds),
                 "correlation": np.eye(len(funds)),
                 "monthly_returns": pd.DataFrame(np.full((48, len(funds)), .006),
                                               columns=[fund.ticker for fund in funds])}
    mandate = Mandate("test", 1, objective_spread=0, minimum_reserve_weight=0)
    monkeypatch.setattr(portfolio, "search_lowest_volatility",
                        lambda *args: (_ for _ in ()).throw(AssertionError("grid search was used")))
    result = portfolio.search_portfolio(estimates, lambda weights, expected: [], mandate, 0, funds, .10)
    assert result["method"] == "optimizer"
    records = [{"ticker": fund.ticker, "role": fund.role} for fund in funds]
    response = server.universe_payload(funds, records,
                                       pd.DataFrame({"month": pd.date_range("2020-01-01", periods=2, freq="MS")}),
                                       .10, mandate)
    assert response["method"] == "optimizer"


def test_role_benchmark_equal_weights_individual_stocks_and_reports_cap_verdict():
    funds = (Fund("SGOV", role="cash"), Fund("IEF", role="government bonds"),
             Fund("AAPL", role="individual stock"), Fund("AXP", role="individual stock"))
    weights = benchmark_weights(funds)
    assert weights == pytest.approx((0, .40, .30, .30))
    mandate = Mandate("test", 1, max_single_stock_weight=.10, max_individual_stocks_total=.40)
    verdicts = mandate.check(weights, {"expected_return": .08}, .02, funds)
    assert not next(row for row in verdicts if row["rule"].startswith("No individual stock"))["pass"]
    assert not next(row for row in verdicts if row["rule"].startswith("Individual stocks combined"))["pass"]


def test_custom_backtest_baselines_rebalance_with_positive_turnover():
    months = pd.date_range("2018-01-01", periods=60, freq="MS")
    returns = pd.DataFrame({"month": months, "SGOV": .001, "IEF": .002,
                            "AAPL": [0.01 if index % 2 else -.005 for index in range(len(months))]})
    request = server.PersonalRequest(savings=1_000, monthly_contribution=0, goal=1_000, years=1,
                                     tolerated_drop=.50, monthly_expenses=0, reserve_months=0)
    funds = (Fund("SGOV", role="cash"), Fund("IEF", role="government bonds"), Fund("AAPL", role="individual stock"))
    summary = server._custom_personal_backtest(request, returns, funds, None)["summary"]
    averages = {row["portfolio"]: row["average_turnover"] for row in summary}
    assert averages["Equal weight"] > 0
    assert averages["60/40 benchmark"] > 0


def test_custom_stock_check_and_no_mix_stop_summary():
    payload = {"portfolios": [{"name": "Your plan", "weights": {"AAA": .5, "BOND": .5},
                                "expected_return": .08, "volatility": .1, "worst_12_month_return": -.1,
                                "simulation": {"chance_of_goal": .8}}],
               "inputs": {"years": 10, "goal": 100}, "objective": {"required_return": .05, "inflation": .02},
               "universe": {"is_default": False, "funds": [{"ticker": "AAA", "role": "individual stock"},
                                                                {"ticker": "BOND", "role": "government bonds"}]},
               "backtest": {"summary": []}, "stress": [], "stop_condition": {"triggered": False}}
    report = server.committee_report("personal", payload)
    check = report["members"][0]["checks"][0]
    assert check["label"] == "Stocks are at least 50%"
    assert check["result"] == "pass"
    summary = server.stop_summary([{"case": "return lower", "weights": None},
                                   {"case": "cost change", "weights": (.5, .5)}], (.5, .5), .20)
    assert summary["no_mix_case_count"] == 1
    assert summary["largest_weight_change"] is None
    assert summary["largest_weight_change_case"] is None


def test_default_universe_shape_and_plain_unknown_ticker_message(monkeypatch):
    client = TestClient(server.app)
    assert isinstance(client.get("/api/universe/default").json()["funds"], list)
    monkeypatch.setattr(server, "universe_details", lambda funds: (_ for _ in ()).throw(ValueError("HTTP Error 404: Not Found")))
    response = client.get("/api/universe/lookup?ticker=xyz")
    assert response.status_code == 422
    assert response.json()["detail"] == "Yahoo Finance does not recognize the ticker XYZ."
