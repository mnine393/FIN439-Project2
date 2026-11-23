"""Offline tests for point-in-time 10-K stock screens."""

import json

import screens


ENDS = ["2022-08-28", "2023-09-03", "2024-09-01", "2025-08-31", "2026-08-30"]
NET_INCOME = [5844, 6292, 7367, 8099, 9226]
CASH_FLOW = [7392, 11068, 11339, 13335, 15817]
CAPEX = [3891, 4323, 4710, 5498, 6435]
EQUITY = [20642, 25058, 23622, 29164, 35803]


def _flow(values, filed="2026-10-01"):
    starts = ["2021-08-29", "2022-08-29", "2023-09-04", "2024-09-02", "2025-09-01"]
    return [
        {
            "form": "10-K",
            "start": start,
            "end": end,
            "filed": filed,
            "accn": end,
            "val": value * 1_000_000,
        }
        for start, end, value in zip(starts, ENDS, values)
    ]


def _instant(values, filed="2026-10-01"):
    return [
        {
            "form": "10-K",
            "end": end,
            "filed": filed,
            "accn": end,
            "val": value * 1_000_000,
        }
        for end, value in zip(ENDS, values)
    ]


def _facts():
    liabilities = [value * 1.4 for value in EQUITY[:-1]] + [EQUITY[-1] * 1.49]
    return {"entityName": "Costco Wholesale", "facts": {"us-gaap": {
        "NetIncomeLoss": {"units": {"USD": _flow(NET_INCOME)}},
        "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": _flow(CASH_FLOW)}},
        "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": _flow(CAPEX)}},
        "StockholdersEquity": {"units": {"USD": _instant(EQUITY)}},
        "Liabilities": {"units": {"USD": _instant(liabilities)}},
    }}}


def _write_cache(directory, facts):
    directory.mkdir(parents=True, exist_ok=True)
    tickers = {"0": {"ticker": "COST", "cik_str": 909832}}
    (directory / "company_tickers.json").write_text(json.dumps(tickers), encoding="utf-8")
    (directory / "companyfacts_0000909832.json").write_text(json.dumps(facts), encoding="utf-8")


def test_costco_reproduces_lab_answers(monkeypatch, tmp_path):
    monkeypatch.setattr(screens, "DATA_DIRECTORY", tmp_path)
    _write_cache(tmp_path, _facts())
    result = screens.screen_stock("cost", "2026-10-15")
    assert result["years"][-1]["roe"] == 9226 / 35803
    assert round(result["years"][-1]["roe"] * 100, 1) == 25.8
    assert result["buffett"]["score"] == "Buffett 3 of 3"
    assert result["burry"]["score"] == "Burry 2 of 2"
    assert result["years"][-1]["liabilities_to_equity"] == 1.49


def test_point_in_time_ignores_later_filing(monkeypatch, tmp_path):
    monkeypatch.setattr(screens, "DATA_DIRECTORY", tmp_path)
    facts = _facts()
    facts["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"][-1]["filed"] = "2026-12-01"
    _write_cache(tmp_path, facts)
    result = screens.screen_stock("COST", "2026-10-15")
    assert len(result["years"]) == 5
    assert result["years"][-1]["net_income"]["value"] is None
    assert result["buffett"]["checks"]["roe_at_least_15_percent_every_year"]["status"] == "not known"


def test_unknown_ticker_is_not_applicable(monkeypatch, tmp_path):
    monkeypatch.setattr(screens, "DATA_DIRECTORY", tmp_path)
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "company_tickers.json").write_text("{}", encoding="utf-8")
    assert screens.screen_stock("FUND")["status"] == "not applicable: no 10-K (fund or foreign filer)"
