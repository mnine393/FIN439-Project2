"""Load point-in-time 13F holdings for the Compass investment legends."""

from __future__ import annotations

import json
import time
import xml.etree.ElementTree as element_tree
from datetime import date, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SEC_USER_AGENT = "Miles Nine mnine@purdue.edu"
DATA_DIRECTORY = Path("data") / "legends"
LEGENDS = {
    "0001067983": "Berkshire Hathaway (Warren Buffett)",
    "0001649339": "Scion Asset Management (Michael Burry)",
}


def _date(value: date | str | None) -> date | None:
    """Convert a supported date value to a date."""
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _cik(cik: str | int) -> str:
    """Return the ten-digit CIK string."""
    return str(cik).zfill(10)


def _request(url: str, body: bytes | None = None, headers: dict | None = None) -> bytes:
    """Make one polite HTTP request with the required SEC identity when applicable."""
    request_headers = dict(headers or {})
    if "sec.gov" in url:
        request_headers["User-Agent"] = SEC_USER_AGENT
    request = Request(url, data=body, headers=request_headers)
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError) as error:
            if attempt == 2:
                raise RuntimeError(f"Request failed for {url}: {error}") from error
            time.sleep(0.5)
    raise RuntimeError(f"Request failed for {url}")


def _download_json(url: str, destination: Path, refresh: bool = False) -> dict:
    """Read a cached JSON document or download and cache it."""
    if destination.exists() and not refresh:
        return json.loads(destination.read_text(encoding="utf-8"))
    time.sleep(0.21)
    payload = _request(url)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return json.loads(payload.decode("utf-8"))


def _download_bytes(url: str, destination: Path, refresh: bool = False) -> bytes:
    """Read a cached document or download and cache it."""
    if destination.exists() and not refresh:
        return destination.read_bytes()
    time.sleep(0.21)
    payload = _request(url)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return payload


def list_13f_filings(cik: str | int, refresh: bool = False) -> list[dict]:
    """Return every 13F-HR or 13F-HR/A filing from the SEC submissions feed."""
    normalized_cik = _cik(cik)
    destination = DATA_DIRECTORY / f"submissions_{normalized_cik}.json"
    url = f"https://data.sec.gov/submissions/CIK{normalized_cik}.json"
    submissions = _download_json(url, destination, refresh)
    feeds = [submissions.get("filings", {}).get("recent", {})]
    for file_info in submissions.get("filings", {}).get("files", []):
        filename = file_info.get("name")
        if not filename:
            continue
        old_path = DATA_DIRECTORY / f"submissions_{normalized_cik}_{filename}"
        feeds.append(_download_json(
            f"https://data.sec.gov/submissions/{filename}",
            old_path,
            refresh,
        ))
    filings = []
    for feed in feeds:
        for index, form in enumerate(feed.get("form", [])):
            if form not in {"13F-HR", "13F-HR/A"}:
                continue
            filings.append({
                "form": form,
                "accession_number": feed["accessionNumber"][index],
                "report_period": feed.get("reportDate", [""])[index],
                "filing_date": feed.get("filingDate", [""])[index],
            })
    return sorted(filings, key=lambda item: (item["filing_date"], item["accession_number"]))


def _local_name(element: element_tree.Element) -> str:
    """Return an XML tag name without its namespace."""
    return element.tag.rsplit("}", 1)[-1]


def _text(row: element_tree.Element, name: str) -> str:
    """Get one direct or nested XML value from an information-table row."""
    for element in row.iter():
        if _local_name(element) == name:
            return (element.text or "").strip()
    return ""


def _parse_holdings(xml_document: bytes, report_period: str) -> list[dict]:
    """Parse SEC information-table XML into uncombined 13F holdings."""
    root = element_tree.fromstring(xml_document)
    multiplier = 1 if _date(report_period) >= date(2023, 1, 1) else 1000
    holdings = []
    for row in root.iter():
        if _local_name(row) != "infoTable":
            continue
        value = _text(row, "value")
        shares = _text(row, "sshPrnamt")
        if not value:
            continue
        holdings.append({
            "issuer": _text(row, "nameOfIssuer"),
            "title_of_class": _text(row, "titleOfClass"),
            "cusip": _text(row, "cusip"),
            "value": int(float(value)) * multiplier,
            "shares": int(float(shares or 0)),
            "put_call": _text(row, "putCall").upper(),
        })
    return holdings


def _filing_xml(cik: str, filing: dict, refresh: bool) -> bytes:
    """Download the filing index and its information-table XML document."""
    accession = filing["accession_number"].replace("-", "")
    bare_cik = str(int(cik))
    base_url = f"https://www.sec.gov/Archives/edgar/data/{bare_cik}/{accession}"
    index_path = DATA_DIRECTORY / f"index_{cik}_{accession}.json"
    index = _download_json(f"{base_url}/index.json", index_path, refresh)
    items = index.get("directory", {}).get("item", [])
    names = [item.get("name", "") for item in items]
    # Filers name the holdings file freely ("infotable.xml", "56757.xml", ...), so open every XML file
    # except the cover page and keep the one that actually contains the information table.
    candidates = [
        name for name in names
        if name.lower().endswith(".xml") and name.lower() != "primary_doc.xml"
    ]
    for filename in candidates:
        path = DATA_DIRECTORY / f"{cik}_{accession}_{filename}"
        document = _download_bytes(f"{base_url}/{filename}", path, refresh)
        if b"informationtable" in document.lower():
            return document
    raise RuntimeError(f"No information-table XML found for {filing['accession_number']}.")


def _combine_holdings(rows: list[dict]) -> list[dict]:
    """Combine reporting rows that share CUSIP and option type."""
    combined: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row["cusip"], row["put_call"])
        if key not in combined:
            combined[key] = dict(row)
            continue
        combined[key]["value"] += row["value"]
        combined[key]["shares"] += row["shares"]
    return list(combined.values())


def _ticker_map(cusips: list[str], refresh: bool = False) -> dict[str, str | None]:
    """Resolve CUSIPs using cached OpenFIGI responses, respecting its anonymous limit."""
    path = DATA_DIRECTORY / "cusip_to_ticker.json"
    mapping = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    needed = sorted(set(cusips) - set(mapping))
    if refresh:
        needed = sorted(set(cusips))
    for start in range(0, len(needed), 10):
        jobs = needed[start:start + 10]
        if start:
            time.sleep(3)
        request_rows = [
            {"idType": "ID_CUSIP", "idValue": value, "exchCode": "US"}
            for value in jobs
        ]
        body = json.dumps(request_rows).encode()
        response = json.loads(_request(
            "https://api.openfigi.com/v3/mapping",
            body,
            {"Content-Type": "application/json"},
        ))
        retry = []
        for cusip, result in zip(jobs, response):
            data = result.get("data", [])
            mapping[cusip] = data[0].get("ticker") if data else None
            if not data:
                retry.append(cusip)
        # Some United States CUSIPs, including foreign issuers that trade in the
        # United States, are omitted when OpenFIGI is given an exchange code.
        # Retry only those misses and retain an explicitly United States or equity
        # result rather than accepting an unrelated instrument.
        if retry:
            retry_body = json.dumps([
                {"idType": "ID_CUSIP", "idValue": cusip} for cusip in retry
            ]).encode()
            retry_response = json.loads(_request(
                "https://api.openfigi.com/v3/mapping",
                retry_body,
                {"Content-Type": "application/json"},
            ))
            for cusip, result in zip(retry, retry_response):
                match = next((item for item in result.get("data", [])
                              if item.get("exchCode") == "US" or item.get("marketSector") == "Equity"), None)
                if match:
                    mapping[cusip] = match.get("ticker")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(mapping, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {cusip: mapping.get(cusip) for cusip in cusips}


def load_holdings(cik: str | int, as_of: date | str | None = None, refresh: bool = False) -> dict:
    """Load the latest 13F publicly filed on or before the requested date."""
    normalized_cik = _cik(cik)
    cutoff = _date(as_of) or date.today()
    eligible = [
        item for item in list_13f_filings(normalized_cik, refresh)
        if _date(item["filing_date"]) <= cutoff
    ]
    if not eligible:
        raise ValueError(f"No 13F filing for CIK {normalized_cik} was filed by {cutoff}.")
    filing = max(eligible, key=lambda item: (item["filing_date"], item["accession_number"]))
    xml_document = _filing_xml(normalized_cik, filing, refresh)
    rows = _combine_holdings(_parse_holdings(xml_document, filing["report_period"]))
    ticker_map = _ticker_map([row["cusip"] for row in rows], refresh)
    for row in rows:
        mapped = ticker_map[row["cusip"]]
        # OpenFIGI writes share classes as "LEN/B"; Yahoo Finance and the SEC use "LEN-B".
        row["ticker"] = mapped.replace("/", "-") if mapped else mapped
    stocks = [row for row in rows if not row["put_call"]]
    options = [row for row in rows if row["put_call"]]
    total = sum(row["value"] for row in stocks)
    for row in stocks:
        row["weight"] = row["value"] / total if total else 0.0
    stocks.sort(key=lambda row: row["value"], reverse=True)
    options.sort(key=lambda row: row["value"], reverse=True)
    return {
        "filer": LEGENDS.get(normalized_cik, normalized_cik),
        "cik": normalized_cik,
        "report_period": filing["report_period"],
        "filing_date": filing["filing_date"],
        "days_to_file": (_date(filing["filing_date"]) - _date(filing["report_period"])).days,
        "holdings": stocks,
        "options": options,
        "unmapped_cusips": sorted({row["cusip"] for row in rows if row["ticker"] is None}),
    }


def legend_summary(cik: str | int, as_of: date | str | None = None, refresh: bool = False) -> dict:
    """Summarize one legend's disclosed stock portfolio and filing freshness."""
    requested_date = _date(as_of) or date.today()
    portfolio = load_holdings(cik, requested_date, refresh)
    holdings = portfolio["holdings"]
    age = (requested_date - _date(portfolio["filing_date"])).days
    stale = age > 200
    return {
        **portfolio,
        "number_of_stock_holdings": len(holdings),
        "top_10": holdings[:10],
        "top_5_weight": sum(row["weight"] for row in holdings[:5]),
        "top_10_weight": sum(row["weight"] for row in holdings[:10]),
        "largest_holding": holdings[0] if holdings else None,
        "stale": stale,
        "stale_message": (
            "Filing is more than 200 days old."
            if stale else "Filing is within 200 days of the requested date."
        ),
    }


def starting_universe(cik: str | int, as_of: date | str | None = None, top_n: int = 10) -> list[dict]:
    """Return the top mapped stock tickers and their disclosed 13F weights."""
    portfolio = load_holdings(cik, as_of)
    rows = [
        {"ticker": row["ticker"], "weight": row["weight"]}
        for row in portfolio["holdings"]
        if row["ticker"]
    ]
    return rows[:top_n]
