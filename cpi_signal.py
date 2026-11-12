"""Point-in-time CPI download and inflation calculation using ALFRED vintages."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd

SERIES_ID = "CPIAUCSL"
DEFAULT_DECISION_DATE = date(2026, 9, 30)
DATA_DIRECTORY = Path("data")
ALFRED_URL = "https://alfred.stlouisfed.org/graph/alfredgraph.csv"


def saved_path(decision_date: date) -> Path:
    return DATA_DIRECTORY / f"cpi_asof_{decision_date.isoformat()}.csv"


def first_publication_path(decision_date: date) -> Path:
    """Return the companion cache for the CPI release date."""
    return DATA_DIRECTORY / f"cpi_first_publication_{decision_date.isoformat()}.csv"


def load_cpi_as_known(decision_date: date = DEFAULT_DECISION_DATE) -> tuple[pd.DataFrame, Path, bool]:
    """Load saved vintage CPI, downloading it only if its local copy is absent."""
    path = saved_path(decision_date)
    if path.exists():
        raw, downloaded = pd.read_csv(path), False
    else:
        DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)
        url = f"{ALFRED_URL}?{urlencode({'id': SERIES_ID, 'vintage_date': decision_date.isoformat()})}"
        raw, downloaded = pd.read_csv(url), True
        raw.to_csv(path, index=False)
    if raw.shape[1] < 2:
        raise ValueError("The CPI download did not contain a value column.")
    value_column = SERIES_ID if SERIES_ID in raw.columns else raw.columns[-1]
    frame = raw.iloc[:, [0, raw.columns.get_loc(value_column)]].copy()
    frame.columns = ["month", "cpi"]
    frame["month"] = pd.to_datetime(frame["month"], errors="coerce")
    frame["cpi"] = pd.to_numeric(frame["cpi"].replace(".", pd.NA), errors="coerce")
    return frame.dropna().sort_values("month").reset_index(drop=True), path, downloaded


def _vintage_contains_month(raw: pd.DataFrame, month: pd.Timestamp) -> bool:
    """Return whether an ALFRED vintage contains the requested observation month."""
    if raw.empty:
        return False
    observations = pd.to_datetime(raw.iloc[:, 0], errors="coerce")
    return (observations == month).any()


def load_first_publication_date(frame: pd.DataFrame, decision_date: date) -> tuple[date, Path, bool]:
    """Find and cache the first ALFRED vintage that contains the latest CPI month.

    ALFRED supplies values as of a vintage date, not a release calendar.  Checking
    every vintage date from that month-end through the decision date identifies the
    first vintage in which the observation appears.
    """
    latest_month = pd.Timestamp(frame["month"].max()).normalize()
    path = first_publication_path(decision_date)
    if path.exists():
        cached = pd.read_csv(path)
        matching = cached[pd.to_datetime(cached["month"], errors="coerce") == latest_month]
        if not matching.empty:
            return pd.Timestamp(matching.iloc[0]["first_publication_date"]).date(), path, False

    month_end = latest_month + pd.offsets.MonthEnd(0)
    if month_end.date() > decision_date:
        raise ValueError("The latest CPI month ends after the decision date.")
    for vintage_date in pd.date_range(month_end, pd.Timestamp(decision_date), freq="D"):
        url = f"{ALFRED_URL}?{urlencode({'id': SERIES_ID, 'vintage_date': vintage_date.date().isoformat()})}"
        raw = pd.read_csv(url)
        if _vintage_contains_month(raw, latest_month):
            DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)
            pd.DataFrame([{"month": latest_month.date().isoformat(),
                           "first_publication_date": vintage_date.date().isoformat()}]).to_csv(path, index=False)
            return vintage_date.date(), path, True
    raise ValueError(f"No ALFRED vintage from {month_end.date()} through {decision_date} contains {latest_month.date()}.")


def cpi_signal(frame: pd.DataFrame, decision_date: date, first_publication_date: date) -> dict[str, object]:
    """Calculate year-over-year CPI from the latest two matching known months."""
    usable = frame[frame["month"] <= pd.Timestamp(decision_date)].copy()
    if usable.empty:
        raise ValueError("No CPI observations were known on the decision date.")
    latest = usable.iloc[-1]
    prior_month = latest["month"] - pd.DateOffset(years=1)
    prior = usable[usable["month"] == prior_month]
    if prior.empty:
        raise ValueError("The saved CPI vintage lacks the month from one year earlier.")
    inflation = float(latest["cpi"] / prior.iloc[-1]["cpi"] - 1)
    return {"inflation": inflation, "month": latest["month"].date(),
            "publication_date": first_publication_date, "cpi": float(latest["cpi"])}


def load_cpi_vintages(decision_dates, refresh: bool = False) -> tuple[pd.DataFrame, bool]:
    """Cache the CPI signal known at each supplied month-end for the backtest."""
    path = DATA_DIRECTORY / "cpi_vintages.csv"
    requested = [pd.Timestamp(value).date() for value in decision_dates]
    existing = pd.read_csv(path) if path.exists() and not refresh else pd.DataFrame()
    # Keep every saved decision date as text so saved and new rows sort together.
    rows = existing.to_dict("records") if not existing.empty else []
    have = set(pd.to_datetime(existing["decision_date"]).dt.date) if not existing.empty else set()
    downloaded = False
    for decision_day in requested:
        if decision_day in have:
            continue
        url = f"{ALFRED_URL}?{urlencode({'id': SERIES_ID, 'vintage_date': decision_day.isoformat()})}"
        raw = pd.read_csv(url)
        value_column = SERIES_ID if SERIES_ID in raw.columns else raw.columns[-1]
        frame = raw.iloc[:, [0, raw.columns.get_loc(value_column)]].copy()
        frame.columns = ["month", "cpi"]
        frame["month"] = pd.to_datetime(frame["month"], errors="coerce")
        frame["cpi"] = pd.to_numeric(frame["cpi"].replace(".", pd.NA), errors="coerce")
        frame = frame.dropna().sort_values("month")
        signal = cpi_signal(frame, decision_day, decision_day)
        rows.append({"decision_date": decision_day.isoformat(), "inflation": signal["inflation"],
                     "cpi_month": signal["month"].isoformat()})
        downloaded = True
        # Save after each download so a network failure keeps the dates already fetched.
        DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).drop_duplicates("decision_date", keep="last").sort_values("decision_date").to_csv(path, index=False)
    result = pd.DataFrame(rows).drop_duplicates("decision_date", keep="last").sort_values("decision_date")
    if downloaded or refresh:
        DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)
        result.to_csv(path, index=False)
    result["decision_date"] = pd.to_datetime(result["decision_date"])
    return result, downloaded
