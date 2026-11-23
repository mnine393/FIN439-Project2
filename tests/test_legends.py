"""Offline tests for SEC 13F legend portfolio loading."""

import json
from datetime import date

import legends


XML = b'''<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
<infoTable><nameOfIssuer>Alpha</nameOfIssuer><titleOfClass>COM</titleOfClass>
<cusip>111111111</cusip><value>100</value><shrsOrPrnAmt><sshPrnamt>10</sshPrnamt>
</shrsOrPrnAmt></infoTable><infoTable><nameOfIssuer>Alpha</nameOfIssuer>
<titleOfClass>COM</titleOfClass><cusip>111111111</cusip><value>50</value>
<shrsOrPrnAmt><sshPrnamt>5</sshPrnamt></shrsOrPrnAmt></infoTable>
<infoTable><nameOfIssuer>Beta</nameOfIssuer><titleOfClass>COM</titleOfClass>
<cusip>222222222</cusip><value>150</value><shrsOrPrnAmt><sshPrnamt>15</sshPrnamt>
</shrsOrPrnAmt></infoTable><infoTable><nameOfIssuer>Put Fund</nameOfIssuer>
<titleOfClass>PUT</titleOfClass><cusip>333333333</cusip><value>25</value>
<putCall>PUT</putCall><shrsOrPrnAmt><sshPrnamt>20</sshPrnamt></shrsOrPrnAmt>
</infoTable></informationTable>'''


def _submissions():
    return {"filings": {"recent": {
        "form": ["13F-HR", "13F-HR/A", "10-K"],
        "accessionNumber": ["0001-01-000001", "0001-01-000002", "0001-01-000003"],
        "reportDate": ["2022-12-31", "2023-03-31", "2023-03-31"],
        "filingDate": ["2023-02-14", "2023-05-15", "2023-05-15"],
    }}}


def test_parser_dollar_formats_and_combines_options():
    old_rows = legends._parse_holdings(XML, "2022-12-31")
    new_rows = legends._parse_holdings(XML, "2023-03-31")
    assert old_rows[0]["value"] == 100_000
    assert new_rows[0]["value"] == 100
    combined = legends._combine_holdings(new_rows)
    stock = next(row for row in combined if row["cusip"] == "111111111")
    assert stock["value"] == 150
    assert any(row["put_call"] == "PUT" for row in combined)


def test_load_holdings_as_of_weights_and_staleness(monkeypatch, tmp_path):
    monkeypatch.setattr(legends, "DATA_DIRECTORY", tmp_path)
    monkeypatch.setattr(legends, "list_13f_filings", lambda cik, refresh=False: [
        {
            "form": "13F-HR", "accession_number": "one", "report_period": "2022-12-31",
            "filing_date": "2023-02-14",
        },
        {
            "form": "13F-HR/A", "accession_number": "two", "report_period": "2023-03-31",
            "filing_date": "2023-05-15",
        },
    ])
    monkeypatch.setattr(legends, "_filing_xml", lambda cik, filing, refresh: XML)
    ticker_map = lambda cusips, refresh=False: {
        "111111111": "AAA", "222222222": "BBB", "333333333": None,
    }
    monkeypatch.setattr(legends, "_ticker_map", ticker_map)
    first = legends.load_holdings("1067983", "2023-04-01")
    assert first["filing_date"] == "2023-02-14"
    loaded = legends.load_holdings("1067983", "2023-06-01")
    assert loaded["filing_date"] == "2023-05-15"
    assert len(loaded["holdings"]) == 2
    assert len(loaded["options"]) == 1
    assert sum(item["weight"] for item in loaded["holdings"]) == 1.0
    summary = legends.legend_summary("1067983", date(2024, 1, 1))
    assert summary["stale"] is True
    assert "more than 200" in summary["stale_message"]


def test_list_filings_uses_saved_submissions(monkeypatch, tmp_path):
    monkeypatch.setattr(legends, "DATA_DIRECTORY", tmp_path)
    path = tmp_path / "submissions_0001067983.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_submissions()), encoding="utf-8")
    filings = legends.list_13f_filings("1067983")
    assert [item["form"] for item in filings] == ["13F-HR", "13F-HR/A"]


def test_filing_index_and_openfigi_response_are_cached(monkeypatch, tmp_path):
    monkeypatch.setattr(legends, "DATA_DIRECTORY", tmp_path)
    index = {"directory": {"item": [{"name": "primary.xml"}, {"name": "informationTable.xml"}]}}
    monkeypatch.setattr(legends, "_download_json", lambda *args: index)
    monkeypatch.setattr(legends, "_download_bytes", lambda *args: XML)
    filing = {"accession_number": "0001-01-000002"}
    assert legends._filing_xml("0001067983", filing, False) == XML
    response = json.dumps([{"data": [{"ticker": "AAA"}]}]).encode("utf-8")
    monkeypatch.setattr(legends, "_request", lambda *args: response)
    assert legends._ticker_map(["111111111"]) == {"111111111": "AAA"}


def test_openfigi_retries_a_united_states_cusip_without_exchange_code(monkeypatch, tmp_path):
    """Keep the fallback needed for issuers OpenFIGI omits from its United States exchange filter."""
    monkeypatch.setattr(legends, "DATA_DIRECTORY", tmp_path)
    calls = []

    def fake_request(url, body=None, headers=None):
        calls.append(json.loads(body.decode("utf-8")))
        if "exchCode" in calls[-1][0]:
            return b'[{"data": []}]'
        return b'[{"data": [{"ticker": "CB", "marketSector": "Equity"}]}]'

    monkeypatch.setattr(legends, "_request", fake_request)
    assert legends._ticker_map(["H1467J104"]) == {"H1467J104": "CB"}
    assert len(calls) == 2
