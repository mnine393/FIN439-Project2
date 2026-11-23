"""Offline coverage for legend portfolio application programming interface responses."""

from datetime import date

import pandas as pd
from fastapi.testclient import TestClient

import server


def _holding(ticker, weight):
    return {"issuer": f"{ticker} Incorporated", "title_of_class": "COM", "ticker": ticker,
            "cusip": ticker * 2, "value": int(weight * 1_000), "shares": 10, "weight": weight,
            "put_call": ""}


def _portfolio(cik, as_of=None, refresh=False):
    holdings = [_holding("AAA", .5), _holding("BBB", .3), _holding("CCC", .2)]
    return {"filer": "Example Filer", "report_period": "2026-06-30", "filing_date": "2026-08-14",
            "days_to_file": 45, "holdings": holdings, "options": [], "unmapped_cusips": ["UNMAPPED"]}


def _summary(cik, as_of=None, refresh=False):
    holdings = _portfolio(cik)["holdings"]
    return {**_portfolio(cik), "number_of_stock_holdings": len(holdings), "top_5_weight": 1.0,
            "top_10_weight": 1.0, "largest_holding": holdings[0], "stale": False,
            "stale_message": "Filing is within 200 days of the requested date."}


def _screen(ticker, as_of=None, refresh=False):
    checks = {"quality": {"status": "pass", "value": 1, "threshold": "at least 1"}}
    return {"ticker": ticker, "company_name": f"{ticker} Incorporated",
            "buffett": {"score": "Buffett 3 of 3", "checks": checks},
            "burry": {"score": "Burry 2 of 2", "checks": checks}}


def test_legend_endpoints_are_point_in_time_and_do_not_backtest(monkeypatch):
    monkeypatch.setattr(server.legends, "load_holdings", _portfolio)
    monkeypatch.setattr(server.legends, "legend_summary", _summary)
    monkeypatch.setattr(server.screens, "screen_stock", _screen)
    server._screen_cached.cache_clear()
    months = pd.date_range("2020-01-01", periods=72, freq="MS")
    variation = [((index % 3) - 1) * .0001 for index in range(len(months))]
    returns = pd.DataFrame({"month": months, "AAA": [.01 + value for value in variation],
                            "BBB": [.008 + value for value in variation],
                            "CCC": [.006 + value for value in variation]})
    records = [{"ticker": ticker, "name": ticker, "role": "individual stock", "reserve_eligible": False,
                "first_month": "2020-01-01", "last_month": "2025-12-01", "downloaded_at": None}
               for ticker in ("AAA", "BBB", "CCC")]
    monkeypatch.setattr(server, "load_universe_returns", lambda funds, **kwargs: (returns, records))
    monkeypatch.setattr(server, "load_cpi_as_known", lambda _: (pd.DataFrame(), None, None))
    monkeypatch.setattr(server, "load_first_publication_date", lambda *args: (date(2026, 9, 1), None, None))
    monkeypatch.setattr(server, "cpi_signal", lambda *args: {"inflation": .02})
    client = TestClient(server.app)
    listing = client.get("/api/legends").json()["buffett"]
    assert {"filer", "person", "report_period", "filing_date", "days_to_file", "number_of_stock_holdings",
            "top_5_weight", "top_10_weight", "largest_holding", "stale", "stale_message"} <= set(listing)
    detail = client.get("/api/legends/buffett?top_n=2").json()
    assert {"holdings", "options", "unmapped_cusips", "screens"} <= set(detail)
    assert detail["screens"][0]["buffett_score"] == "3 of 3"
    universe = client.get("/api/legends/buffett/universe?top_n=2").json()
    assert universe["universe"][0]["role"] == "individual stock"
    assert universe["suggested_additions"][0]["ticker"] == "SGOV"
    analysis = client.get("/api/legends/buffett/analysis?top_n=3").json()
    assert {"expected_return", "volatility", "worst_12_month_return", "effective_number_of_holdings",
            "verdicts", "simulation", "hindsight_note"} <= set(analysis)
    assert "backtest" not in analysis
    assert analysis["hindsight_note"].startswith("These weights come from the filing dated 2026-08-14")


def test_custom_personal_stocks_include_screens_and_committee_checks(monkeypatch):
    monkeypatch.setattr(server.screens, "screen_stock", _screen)
    server._screen_cached.cache_clear()
    months = pd.date_range("2020-01-01", periods=72, freq="MS")
    variation = [((index % 3) - 1) * .0001 for index in range(len(months))]
    returns = pd.DataFrame({"month": months, "AAA": [.01 + value for value in variation],
                            "BBB": [.009 + value for value in variation],
                            "CCC": [.008 + value for value in variation],
                            "SGOV": [.002 + value for value in variation],
                            "IEF": [.003 + value for value in variation]})
    records = [{"ticker": ticker, "name": ticker, "role": "individual stock" if ticker in {"AAA", "BBB", "CCC"}
                else "cash" if ticker == "SGOV" else "government bonds", "reserve_eligible": ticker in {"SGOV", "IEF"},
                "first_month": "2020-01-01", "last_month": "2025-12-01", "downloaded_at": None,
                "instrument_type": "EQUITY" if ticker in {"AAA", "BBB", "CCC"} else "ETF"}
               for ticker in ("AAA", "BBB", "CCC", "SGOV", "IEF")]
    monkeypatch.setattr(server, "load_universe_returns", lambda funds, **kwargs: (returns, records))
    monkeypatch.setattr(server, "load_cpi_as_known", lambda _: (pd.DataFrame(), None, None))
    monkeypatch.setattr(server, "load_first_publication_date", lambda *args: (date(2026, 9, 1), None, None))
    monkeypatch.setattr(server, "cpi_signal", lambda *args: {"inflation": .02, "month": date(2026, 8, 1)})
    response = TestClient(server.app).post("/api/personal/plan", json={
        "savings": 100_000, "monthly_contribution": 0, "goal": 100_000, "years": 10,
        "tolerated_drop": .9, "monthly_expenses": 0, "reserve_months": 0,
        "universe": [{"ticker": ticker, "role": "individual stock", "reserve_eligible": False}
                     for ticker in ("AAA", "BBB", "CCC")] + [
            {"ticker": "SGOV", "role": "cash", "reserve_eligible": True},
            {"ticker": "IEF", "role": "government bonds", "reserve_eligible": True},
        ]})
    payload = response.json()
    assert response.status_code == 200
    assert len(payload["screens"]) == 3
    checks = [check["label"] for member in payload["committee"]["members"] for check in member["checks"]]
    assert "Every individual stock in the plan passes Buffett's checks" in checks
    assert "Every individual stock in the plan passes Burry's checks" in checks
