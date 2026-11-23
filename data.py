"""Offline monthly return data for the Endowment Command Center."""
from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

import pandas as pd

from get_prices import yahoo_adjusted_close
from universe import Fund

DATA_DIRECTORY = Path("data")
MONTHLY_RETURNS_FILE = DATA_DIRECTORY / "monthly_returns.csv"
PRICE_DIRECTORY = DATA_DIRECTORY / "prices"
FUNDS = ("SGOV", "IEF", "USIG", "VT")
START_MONTH = pd.Timestamp("2008-07-01")
END_MONTH = pd.Timestamp("2026-09-01")


def treasury_bill_proxy_return(annual_rate_percent: float) -> float:
    """Convert the monthly quoted annual three-month Treasury bill rate to a return."""
    return float(annual_rate_percent) / 12 / 100


def _fred_three_month_bill_rates() -> pd.Series:
    # FRED drops requests with a browser-style or custom User-Agent, so send Python's default one.
    request = Request("https://fred.stlouisfed.org/graph/fredgraph.csv?id=TB3MS")
    with urlopen(request, timeout=60) as response:
        raw = pd.read_csv(response)
    raw.columns = ["month", "rate"]
    raw["month"] = pd.to_datetime(raw["month"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    raw["rate"] = pd.to_numeric(raw["rate"], errors="coerce")
    return raw.dropna().set_index("month")["rate"]


def download_monthly_returns(end_month: pd.Timestamp = END_MONTH) -> pd.DataFrame:
    """Download fund total returns and the pre-SGOV Treasury bill cash proxy."""
    # An extra prior month supplies the July 2008 total return.
    start_for_prices = (START_MONTH - pd.DateOffset(months=1)).date()
    end_exclusive = (pd.Timestamp(end_month) + pd.DateOffset(months=1)).date()
    prices = {fund: yahoo_adjusted_close(fund, start_for_prices, end_exclusive) for fund in FUNDS}
    price_frame = pd.DataFrame({fund: pd.Series(values, dtype=float) for fund, values in prices.items()})
    price_frame.index = pd.to_datetime(price_frame.index)
    price_frame.index.name = "month"
    fund_returns = price_frame.pct_change(fill_method=None)

    required = fund_returns[["IEF", "USIG", "VT"]].dropna().index
    months = required[(required >= START_MONTH) & (required <= pd.Timestamp(end_month))]
    rates = _fred_three_month_bill_rates()
    first_sgov_observation = pd.Timestamp(min(prices["SGOV"]))
    first_full_sgov_month = first_sgov_observation + pd.DateOffset(months=1)
    rows = []
    for month in months:
        if month >= first_full_sgov_month and pd.notna(fund_returns.loc[month, "SGOV"]):
            sgov_return, source = float(fund_returns.loc[month, "SGOV"]), "SGOV actual"
        else:
            if month not in rates.index:
                raise ValueError(f"Missing three-month Treasury bill rate for {month.date()}.")
            sgov_return = treasury_bill_proxy_return(rates.loc[month])
            source = "Treasury bill proxy"
        rows.append({"month": month.date().isoformat(), "SGOV": sgov_return,
                     "IEF": float(fund_returns.loc[month, "IEF"]),
                     "USIG": float(fund_returns.loc[month, "USIG"]),
                     "VT": float(fund_returns.loc[month, "VT"]), "sgov_source": source})
    return pd.DataFrame(rows)


def load_monthly_returns(refresh: bool = False) -> tuple[pd.DataFrame, bool]:
    """Read the local return file, downloading only when absent or requested."""
    if refresh or not MONTHLY_RETURNS_FILE.exists():
        DATA_DIRECTORY.mkdir(exist_ok=True)
        frame = download_monthly_returns()
        frame.to_csv(MONTHLY_RETURNS_FILE, index=False)
        downloaded = True
    else:
        frame, downloaded = pd.read_csv(MONTHLY_RETURNS_FILE), False
    required = ["month", *FUNDS, "sgov_source"]
    if list(frame.columns) != required:
        raise ValueError("monthly_returns.csv has unexpected columns.")
    frame["month"] = pd.to_datetime(frame["month"], errors="coerce")
    for fund in FUNDS:
        frame[fund] = pd.to_numeric(frame[fund], errors="coerce")
    if frame[required[:-1]].isna().any().any() or not frame["month"].is_monotonic_increasing:
        raise ValueError("monthly_returns.csv must contain complete oldest-first monthly data.")
    return frame, downloaded


def _price_paths(ticker: str) -> tuple[Path, Path]:
    """Return the saved price and metadata paths for one ticker."""
    return PRICE_DIRECTORY / f"{ticker}.csv", PRICE_DIRECTORY / f"{ticker}.json"


def _download_ticker(ticker: str) -> tuple[dict, str, str]:
    """Download all available monthly prices and the Yahoo long name."""
    from urllib.parse import quote
    from urllib.request import Request, urlopen

    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(ticker)}"
           "?period1=0&period2=4102444800&interval=1mo&events=history&includeAdjustedClose=true")
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    result = payload.get("chart", {}).get("result")
    if not result:
        raise ValueError(f"Yahoo Finance does not recognize ticker {ticker}.")
    series = result[0]
    adjusted = series.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose", [])
    prices = {}
    for stamp, value in zip(series.get("timestamp", []), adjusted):
        if value is not None:
            month = datetime.fromtimestamp(stamp, tz=timezone.utc).date().replace(day=1)
            prices[month.isoformat()] = float(value)
    if not prices:
        raise ValueError(f"Yahoo Finance does not have monthly prices for {ticker}.")
    meta = series.get("meta", {})
    return prices, str(meta.get("longName") or meta.get("shortName") or ticker), str(meta.get("instrumentType") or "")


def load_fund_prices(fund: Fund, refresh: bool = False) -> tuple[pd.Series, dict]:
    """Read or download one fund's monthly adjusted closes and metadata."""
    csv_path, json_path = _price_paths(fund.ticker)
    if refresh or not csv_path.exists():
        failure = None
        for attempt in range(3):
            try:
                prices, name, instrument_type = _download_ticker(fund.ticker)
                break
            except Exception as error:
                failure = error
                if attempt < 2:
                    time.sleep(.25)
        else:
            raise ValueError(str(failure)) from failure
        PRICE_DIRECTORY.mkdir(parents=True, exist_ok=True)
        frame = pd.DataFrame({"month": sorted(prices), "adjusted_close": [prices[key] for key in sorted(prices)]})
        frame.to_csv(csv_path, index=False)
        metadata = {"name": name, "first_month": frame["month"].iloc[0],
                    "last_month": frame["month"].iloc[-1],
                    "downloaded_at": datetime.now(timezone.utc).isoformat(),
                    "instrument_type": instrument_type}
        json_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    else:
        frame = pd.read_csv(csv_path)
        metadata = json.loads(json_path.read_text(encoding="utf-8")) if json_path.exists() else {
            "name": fund.ticker, "first_month": str(frame["month"].iloc[0]),
            "last_month": str(frame["month"].iloc[-1]), "downloaded_at": None,
        }
    months = pd.to_datetime(frame["month"], errors="coerce")
    values = pd.to_numeric(frame["adjusted_close"], errors="coerce")
    if months.isna().any() or values.isna().any() or (values <= 0).any():
        raise ValueError(f"Saved prices for {fund.ticker} are invalid.")
    return pd.Series(values.to_numpy(), index=months, name=fund.ticker), metadata


def load_universe_returns(funds: tuple[Fund, ...], refresh: bool = False,
                          decision_date: date | None = None) -> tuple[pd.DataFrame, list[dict]]:
    """Build total returns over the common complete monthly window for a custom universe."""
    series = {}
    records = []
    cutoff = pd.Timestamp(decision_date or date.today()).replace(day=1)
    for fund in funds:
        prices, metadata = load_fund_prices(fund, refresh)
        series[fund.ticker] = prices[prices.index <= cutoff]
        records.append({"ticker": fund.ticker, "name": metadata.get("name") or fund.name or fund.ticker,
                        "role": fund.role, "reserve_eligible": fund.reserve_eligible,
                        "first_month": metadata["first_month"], "last_month": metadata["last_month"],
                        "downloaded_at": metadata.get("downloaded_at"),
                        "instrument_type": metadata.get("instrument_type")})
    # These references support historical crisis proxies without becoming holdings.
    for ticker, role in (("VT", "stocks"), ("IEF", "government bonds")):
        if ticker not in series:
            prices, _ = load_fund_prices(Fund(ticker, role=role), refresh)
            series[ticker] = prices[prices.index <= cutoff]
    prices = pd.DataFrame(series)
    returns = prices.pct_change(fill_method=None)
    proxy_extensions = {}
    proxy_months_by_ticker = {}
    cash_funds = [fund for fund in funds if fund.role == "cash"]
    if cash_funds:
        # The saved default data already contains the documented FRED TB3MS / 12
        # cash proxy.  Reusing it keeps custom histories on the same basis as the
        # default universe without making an analysis request download new data.
        default_returns, _ = load_monthly_returns()
        bill_proxy = default_returns.set_index("month")["SGOV"]
        for fund in cash_funds:
            actual = returns[fund.ticker].dropna()
            if actual.empty:
                continue
            first_full_month = actual.index.min()
            missing_before_actual = returns.index < first_full_month
            proxy_months = returns.index[missing_before_actual & returns[fund.ticker].isna()]
            usable_months = proxy_months.intersection(bill_proxy.index)
            if len(usable_months):
                returns.loc[usable_months, fund.ticker] = bill_proxy.loc[usable_months]
                proxy_extensions[fund.ticker] = usable_months.min().date().isoformat()
                proxy_months_by_ticker[fund.ticker] = usable_months
    for record in records:
        record["proxy_extension_start"] = proxy_extensions.get(record["ticker"])
    common_returns = returns[[fund.ticker for fund in funds]].dropna().copy()
    if len(common_returns) < 60:
        shortest = max(records, key=lambda row: row["first_month"])
        raise ValueError(f"Common history is shorter than 60 months; {shortest['ticker']} starts {shortest['first_month']}.")
    for fund in cash_funds:
        source = pd.Series(f"{fund.ticker} actual", index=common_returns.index, dtype=object)
        proxy_months = proxy_months_by_ticker.get(fund.ticker, pd.DatetimeIndex([]))
        source.loc[source.index.intersection(proxy_months)] = "Treasury bill proxy"
        common_returns[f"{fund.ticker.lower()}_source"] = source
    common_returns.insert(0, "month", common_returns.index)
    result = common_returns.reset_index(drop=True)
    return result, records


def load_crisis_reference_returns(funds: tuple[Fund, ...], refresh: bool = False,
                                  decision_date: date | None = None) -> pd.DataFrame:
    """Load full holding and reference return history for crisis replays only."""
    cutoff = pd.Timestamp(decision_date or date.today()).replace(day=1)
    series = {}
    references = (Fund("VT", role="stocks"), Fund("IEF", role="government bonds"))
    for fund in (*funds, *references):
        if fund.ticker not in series:
            prices, _ = load_fund_prices(fund, refresh)
            series[fund.ticker] = prices[prices.index <= cutoff]
    returns = pd.DataFrame(series).pct_change(fill_method=None)
    returns.insert(0, "month", returns.index)
    return returns.reset_index(drop=True)
