"""Run offline-cacheable Buffett and Burry stock screens from SEC 10-K facts."""

from __future__ import annotations

import json
import re
import time
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SEC_USER_AGENT = "Miles Nine mnine@purdue.edu"
DATA_DIRECTORY = Path("data") / "screens"
ANNUAL_DAYS_MIN = 350
ANNUAL_DAYS_MAX = 380
METRICS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"],
    "net_income": ["NetIncomeLoss"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "capital_spending": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
    "equity": ["StockholdersEquity"],
    "liabilities": ["Liabilities"],
}
INSTANT_METRICS = {"equity", "liabilities"}


def _date(value: date | str | None) -> date | None:
    """Convert a date string to a date."""
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _request(url: str) -> bytes:
    """Fetch an SEC document with the required identity and bounded retries."""
    request = Request(url, headers={"User-Agent": SEC_USER_AGENT})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError) as error:
            if attempt == 2:
                raise RuntimeError(f"SEC request failed for {url}: {error}") from error
            time.sleep(0.5)
    raise RuntimeError(f"SEC request failed for {url}")


def _cached_json(url: str, path: Path, refresh: bool = False) -> dict:
    """Load a JSON cache file or download it once."""
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    time.sleep(0.21)
    payload = _request(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return json.loads(payload.decode("utf-8"))


def _ticker(value: str) -> str:
    """Validate and normalize an equity ticker."""
    # Share classes arrive as "LEN/B" from OpenFIGI; Yahoo Finance and the SEC write them "LEN-B".
    normalized = value.strip().upper().replace("/", "-")
    if not re.fullmatch(r"[A-Z.\-]{1,12}", normalized):
        raise ValueError("Ticker must contain only letters, periods, or hyphens.")
    return normalized


def _cik_for_ticker(ticker: str, refresh: bool = False) -> str | None:
    """Find a CIK for a ticker from the saved SEC company ticker list."""
    records = _cached_json(
        "https://www.sec.gov/files/company_tickers.json",
        DATA_DIRECTORY / "company_tickers.json",
        refresh,
    )
    for record in records.values():
        if record.get("ticker", "").upper() == ticker:
            cik = record.get("cik_str")
            return str(cik).zfill(10) if cik else None
    return None


def _latest(candidates: list[dict]) -> dict:
    """Return the latest filed candidate for one fiscal period."""
    return max(candidates, key=lambda item: (item.get("filed", ""), item.get("accn", "")))


def _metric_values(company_facts: dict, metric: str, cutoff: date) -> dict[str, dict]:
    """Select annual 10-K fact values by tag priority and latest known filing."""
    facts = company_facts.get("facts", {}).get("us-gaap", {})
    result: dict[str, dict] = {}
    for tag in METRICS[metric]:
        fact = facts.get(tag, {})
        candidates: dict[str, list[dict]] = {}
        for unit_values in fact.get("units", {}).values():
            for item in unit_values:
                if item.get("form") != "10-K" or not item.get("end") or not item.get("filed"):
                    continue
                if _date(item["filed"]) > cutoff:
                    continue
                if metric in INSTANT_METRICS:
                    valid = not item.get("start")
                else:
                    if not item.get("start"):
                        valid = False
                    else:
                        duration = (_date(item["end"]) - _date(item["start"])).days
                        valid = ANNUAL_DAYS_MIN <= duration <= ANNUAL_DAYS_MAX
                if valid:
                    candidates.setdefault(item["end"], []).append(item)
        for fiscal_end, values in candidates.items():
            selected = _latest(values)
            result.setdefault(fiscal_end, {
                "value": selected.get("val"),
                "tag": tag,
                "filed": selected["filed"],
            })
    return result


def _status(value: bool | None) -> str:
    """Render a nullable boolean check."""
    if value is None:
        return "not known"
    return "pass" if value else "fail"


def _check(status: str, value: object, threshold: str) -> dict:
    """Build a consistently shaped screen check result."""
    return {"status": status, "value": value, "threshold": threshold}


def screen_stock(ticker: str, as_of: date | str | None = None, refresh: bool = False) -> dict:
    """Screen one common stock using only 10-K facts public on the requested date."""
    symbol = _ticker(ticker)
    cutoff = _date(as_of) or date.today()
    cik = _cik_for_ticker(symbol, refresh)
    if cik is None:
        return {"ticker": symbol, "status": "not applicable: no 10-K (fund or foreign filer)"}
    facts = _cached_json(
        f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
        DATA_DIRECTORY / f"companyfacts_{cik}.json",
        refresh,
    )
    sources = {metric: _metric_values(facts, metric, cutoff) for metric in METRICS}
    years = sorted({end for values in sources.values() for end in values})[-5:]
    if not years:
        return {"ticker": symbol, "cik": cik, "status": "not applicable: no 10-K (fund or foreign filer)"}
    records = []
    for fiscal_end in years:
        row = {"fiscal_year_end": fiscal_end}
        for metric in METRICS:
            row[metric] = sources[metric].get(fiscal_end, {"value": None, "tag": "not found"})
        income = row["net_income"]["value"]
        equity = row["equity"]["value"]
        cash_flow = row["operating_cash_flow"]["value"]
        spending = row["capital_spending"]["value"]
        liabilities = row["liabilities"]["value"]
        row["roe"] = None if income is None or not equity or equity <= 0 else income / equity
        row["owner_earnings"] = None if cash_flow is None or spending is None else cash_flow - spending
        row["liabilities_to_equity"] = (
            None if liabilities is None or not equity or equity <= 0 else liabilities / equity
        )
        records.append(row)
    roe_values = [None if row["roe"] is None else row["roe"] >= 0.15 for row in records]
    owner_values = [None if row["owner_earnings"] is None else row["owner_earnings"] > 0 for row in records]
    first_owner = records[0]["owner_earnings"]
    last_owner = records[-1]["owner_earnings"]
    growth = None if first_owner is None or last_owner is None else last_owner > first_owner
    cash_values = [
        None if row["operating_cash_flow"]["value"] is None or row["net_income"]["value"] is None
        else row["operating_cash_flow"]["value"] >= row["net_income"]["value"]
        for row in records
    ]
    latest_ratio = records[-1]["liabilities_to_equity"]
    buffett = {
        "roe_at_least_15_percent_every_year": _check(
            _status(None if None in roe_values else all(roe_values)),
            [row["roe"] for row in records],
            ">= 15% every year",
        ),
        "owner_earnings_positive_every_year": _check(
            _status(None if None in owner_values else all(owner_values)),
            [row["owner_earnings"] for row in records],
            "> 0 every year",
        ),
        "owner_earnings_grew_first_to_last": _check(
            _status(growth),
            {"first": first_owner, "last": last_owner},
            "last > first",
        ),
    }
    burry = {
        "operating_cash_flow_at_least_net_income_every_year": _check(
            _status(None if None in cash_values else all(cash_values)),
            [(row["operating_cash_flow"]["value"], row["net_income"]["value"]) for row in records],
            "operating cash flow >= net income every year",
        ),
        "liabilities_no_more_than_twice_equity_latest_year": _check(
            _status(None if latest_ratio is None else latest_ratio <= 2),
            latest_ratio,
            "<= 2.0x",
        ),
    }
    return {
        "ticker": symbol,
        "cik": cik,
        "company_name": facts.get("entityName", "not found"),
        "as_of": cutoff.isoformat(),
        "years": records,
        "buffett": {
            "checks": buffett,
            "score": f"Buffett {sum(item['status'] == 'pass' for item in buffett.values())} of 3",
        },
        "burry": {
            "checks": burry,
            "score": f"Burry {sum(item['status'] == 'pass' for item in burry.values())} of 2",
        },
    }


def screen_universe(tickers: list[str], as_of: date | str | None = None) -> list[dict]:
    """Screen each ticker in the supplied universe."""
    return [screen_stock(ticker, as_of) for ticker in tickers]
