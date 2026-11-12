"""Offline monthly return data for the Endowment Command Center."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

from get_prices import yahoo_adjusted_close

DATA_DIRECTORY = Path("data")
MONTHLY_RETURNS_FILE = DATA_DIRECTORY / "monthly_returns.csv"
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
