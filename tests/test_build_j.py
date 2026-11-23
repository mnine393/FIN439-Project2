"""Regression coverage for the Build J custom-analysis return tables."""

from datetime import date

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

import analyze
import data
import forecast
import server
from universe import Fund


def _prices(fund, refresh=False):
    months = pd.date_range("2007-01-01", "2026-10-01", freq="MS")
    position = np.arange(len(months))
    offset = sum(map(ord, fund.ticker)) % 7
    returns = .003 + offset * .0002 + .002 * np.sin(position / (5 + offset))
    values = 100 * np.cumprod(1 + returns)
    return pd.Series(values, index=months, name=fund.ticker), {
        "name": fund.ticker, "first_month": months[0].date().isoformat(),
        "last_month": months[-1].date().isoformat(), "downloaded_at": None,
        "instrument_type": "ETF",
    }


def _fred(series):
    return pd.Series([2.0, 3.0], index=pd.to_datetime(["2007-01-31", "2026-09-30"]), name=series)


def test_custom_return_tables_have_no_attrs_and_analysis_endpoints_work_offline(monkeypatch):
    monkeypatch.setattr(data, "load_fund_prices", _prices)
    monkeypatch.setattr(forecast, "fetch_fred_series", _fred)
    monkeypatch.setattr(analyze, "fetch_fred_series", _fred)
    funds = (Fund("VTI", role="stocks"), Fund("VXUS", role="stocks"), Fund("BND", role="broad bonds"))
    returns, _ = data.load_universe_returns(funds, decision_date=date(2026, 10, 1))
    crisis_returns = data.load_crisis_reference_returns(funds, decision_date=date(2026, 10, 1))
    assert returns.attrs == {}
    assert crisis_returns.attrs == {}

    client = TestClient(server.app)
    sections = {"weights", "total_value", "allocation_by_role", "history", "risk_contribution",
                "diversification_ratio", "correlation", "drawdown_series", "growth_of_10000",
                "risk_score", "concentration", "fees", "forecast", "crisis_scenarios", "flags"}
    portfolios = ({"VT": 60_000, "IEF": 40_000}, {"VTI": 50_000, "VXUS": 30_000, "BND": 20_000})
    for holdings in portfolios:
        response = client.post("/api/analyze", json={"holdings": holdings, "horizon_years": 1})
        assert response.status_code == 200
        assert sections <= set(response.json())

        response = client.post("/api/compare", json={"a": holdings, "b": holdings, "horizon_years": 1})
        assert response.status_code == 200
        payload = response.json()
        assert {"a", "b", "differences", "details"} <= set(payload)
        assert sections <= set(payload["details"]["a"])
        assert sections <= set(payload["details"]["b"])
