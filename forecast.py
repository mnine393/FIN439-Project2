"""Forward-looking, point-in-time portfolio forecasts."""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

from universe import Fund

EQUITY_RISK_PREMIUM = 0.045
FRED_DIRECTORY = Path("data/fred")
FRED_SERIES = ("TB3MS", "GS10", "BAA")
ONE_DAY_SECONDS = 24 * 60 * 60


def _fred_path(series_id: str) -> Path:
    """Return the local cache location for one FRED series."""
    return FRED_DIRECTORY / f"{series_id}.csv"


def _read_fred_file(path: Path) -> pd.DataFrame:
    """Read and standardize a saved FRED comma-separated file."""
    frame = pd.read_csv(path)
    frame.columns = ["date", "value"]
    return frame


def _fred_fallback(series_id: str) -> pd.Series:
    """Return the documented offline fallback for an unavailable yield."""
    if series_id == "TB3MS":
        source = pd.read_csv("data/monthly_returns.csv")
        dates = pd.to_datetime(source["month"]) + pd.offsets.MonthEnd(0)
        values = source["SGOV"] * 1200
        return pd.Series(values.to_numpy(), index=dates, name=series_id)
    index = pd.DatetimeIndex([pd.Timestamp("1900-01-31")])
    return pd.Series([4.0], index=index, name=series_id)


@lru_cache(maxsize=None)
def _load_fred_series(series_id: str) -> pd.Series:
    """Load one series once per process, refreshing only stale saved data."""
    path = _fred_path(series_id)
    is_fresh = path.exists() and time.time() - path.stat().st_mtime < ONE_DAY_SECONDS
    frame = None
    if is_fresh:
        try:
            frame = _read_fred_file(path)
        except Exception:
            frame = None
    if frame is None:
        try:
            request = Request(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}")
            with urlopen(request, timeout=10) as response:
                frame = pd.read_csv(response)
            frame.columns = ["date", "value"]
            FRED_DIRECTORY.mkdir(parents=True, exist_ok=True)
            frame.to_csv(path, index=False)
        except Exception:
            try:
                frame = _read_fred_file(path)
            except Exception:
                return _fred_fallback(series_id)
    dates = pd.to_datetime(frame["date"], errors="coerce")
    index = dates.dt.to_period("M").dt.to_timestamp("M")
    values = pd.to_numeric(frame["value"], errors="coerce")
    series = pd.Series(values.to_numpy(), index=index, name=series_id)
    return series.dropna().sort_index()


def fetch_fred_series(series_id: str) -> pd.Series:
    """Return a month-end FRED series from the process and disk caches."""
    return _load_fred_series(series_id).copy()


def _returns_frame(returns: pd.DataFrame) -> pd.DataFrame:
    """Standardize monthly return dates and retain numeric holding columns."""
    frame = returns.copy()
    if "month" in frame:
        if pd.api.types.is_numeric_dtype(frame["month"]):
            raise ValueError("Forecast returns need month dates; got an undated table.")
        frame = frame.set_index("month")
    elif not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError("Forecast returns need month dates; got an undated table.")
    dates = pd.to_datetime(frame.index)
    if dates.isna().any():
        raise ValueError("Forecast returns need month dates; got an undated table.")
    frame.index = dates.to_period("M").to_timestamp("M")
    return frame.select_dtypes(include=[np.number]).sort_index()


def _beta(column: pd.Series, frame: pd.DataFrame, funds: tuple[Fund, ...]) -> float:
    """Estimate a Blume-adjusted market beta from available monthly returns."""
    if "VT" in frame:
        reference = frame["VT"]
    else:
        stock_tickers = [fund.ticker for fund in funds if fund.role in {"stocks", "individual stock"} and fund.ticker in frame]
        reference = frame[stock_tickers].mean(axis=1) if stock_tickers else None
    if reference is None:
        return 1.0
    common = pd.concat([column, reference], axis=1).dropna()
    if len(common) < 2 or common.iloc[:, 1].var() == 0:
        return 1.0
    raw_beta = common.iloc[:, 0].cov(common.iloc[:, 1]) / common.iloc[:, 1].var()
    return float(0.67 * raw_beta + 0.33)


def _yield_information(yields: dict[str, pd.Series], cutoff: pd.Timestamp) -> tuple[dict, dict]:
    """Limit yield data to the decision date and describe its latest dates."""
    latest = {}
    dates = {}
    for name in FRED_SERIES:
        series = yields[name].loc[:cutoff]
        latest[name] = float(series.iloc[-1]) / 100 if len(series) else 0.04
        dates[name] = series.index[-1].date().isoformat() if len(series) and series.index[-1].year != 1900 else "documented fallback"
    return latest, dates


def capital_market_assumptions(funds, returns, as_of, blend: float = 0.5, yields=None) -> dict:
    """Build annual assumptions using returns and yields known by ``as_of``."""
    funds = tuple(funds)
    frame = _returns_frame(returns)
    cutoff = frame.index.max() if as_of is None else pd.Timestamp(as_of).to_period("M").to_timestamp("M")
    frame = frame.loc[:cutoff]
    supplied_yields = yields or {name: fetch_fred_series(name) for name in FRED_SERIES}
    latest, yield_dates = _yield_information(supplied_yields, cutoff)
    bond_roles = {"government bonds", "broad bonds", "inflation-protected bonds"}
    result = {}
    for fund in funds:
        history = frame[fund.ticker].dropna() if fund.ticker in frame else pd.Series(dtype=float)
        history_mean = float(history.mean() * 12) if len(history) else 0.0
        if fund.role == "cash":
            forward_estimate = latest["TB3MS"]
            source = "three-month Treasury bill yield"
        elif fund.role in bond_roles:
            forward_estimate = latest["GS10"]
            source = "ten-year Treasury yield"
        elif fund.role == "corporate bonds":
            forward_estimate = latest["BAA"] - 0.01
            source = "Baa corporate yield less expected defaults"
        else:
            beta = _beta(frame[fund.ticker], frame, funds) if fund.ticker in frame else 1.0
            forward_estimate = latest["TB3MS"] + beta * EQUITY_RISK_PREMIUM
            source = f"bill yield plus {beta:.2f} beta times equity risk premium"
        result[fund.ticker] = {"history_mean": history_mean, "forward_estimate": float(forward_estimate), "blended": float(blend * forward_estimate + (1 - blend) * history_mean), "basis": f"Forward estimate uses {source}; history uses monthly returns known by {cutoff.date()}.", "yield_dates": yield_dates}
    return result


def _history_assumptions(funds, frame: pd.DataFrame) -> dict:
    """Keep the simple method's assumption field without requesting yields."""
    result = {}
    for fund in funds:
        history_mean = float(frame[fund.ticker].dropna().mean() * 12)
        result[fund.ticker] = {"history_mean": history_mean, "forward_estimate": history_mean, "blended": history_mean, "basis": "Simple method uses monthly returns known by the forecast date.", "yield_dates": {}}
    return result


def shrunk_covariance(monthly_returns: pd.DataFrame) -> tuple[np.ndarray, float]:
    """Return annual covariance using simplified constant-correlation shrinkage.

    This Ledoit-Wolf-style target intentionally omits the full rho term, so its
    data-driven intensity is an approximation rather than the full formula.
    """
    values = np.asarray(monthly_returns, dtype=float)
    values = values[np.all(np.isfinite(values), axis=1)]
    sample = np.cov(values, rowvar=False, ddof=1)
    if values.shape[1] == 1:
        return np.atleast_2d(sample * 12), 1.0
    standard_deviations = np.sqrt(np.maximum(np.diag(sample), 1e-16))
    correlation = sample / np.outer(standard_deviations, standard_deviations)
    average_correlation = (correlation.sum() - len(standard_deviations)) / (len(standard_deviations) * (len(standard_deviations) - 1))
    target = average_correlation * np.outer(standard_deviations, standard_deviations)
    np.fill_diagonal(target, np.diag(sample))
    delta = float(np.sum((sample - target) ** 2))
    centered = values - values.mean(axis=0)
    outer_products = centered[:, :, None] * centered[:, None, :]
    phi = float(np.mean(np.sum((outer_products - sample) ** 2, axis=(1, 2))))
    intensity = float(np.clip(phi / max(delta * len(values), 1e-16), 0, 1))
    return ((1 - intensity) * sample + intensity * target) * 12, intensity


def _block_draws(count: int, months: int, block_months: int, rng, paths: int = 1) -> np.ndarray:
    """Draw circular, consecutive monthly blocks for every simulation path."""
    number_of_blocks = int(np.ceil(months / block_months))
    starts = rng.integers(0, count, size=(paths, number_of_blocks))
    blocks = (starts[:, :, None] + np.arange(block_months)) % count
    return blocks.reshape(paths, -1)[:, :months]


def _mean_adjustment(draws: np.ndarray, frame: pd.DataFrame, assumptions: dict, tickers: list[str]) -> np.ndarray:
    """Shift sampled returns so their means match point-in-time assumptions."""
    targets = np.array([assumptions[ticker]["blended"] / 12 for ticker in tickers])
    return draws + targets - frame.mean().to_numpy()


def _parameter_shift(draws: np.ndarray, frame: pd.DataFrame, rng) -> np.ndarray:
    """Add one path-specific mean error to reflect estimated-return uncertainty."""
    errors = frame.std(ddof=1).to_numpy() / np.sqrt(len(frame))
    shifts = rng.normal(0, errors, size=(len(draws), frame.shape[1]))
    return draws + shifts[:, None, :]


def _percentile_values(values: np.ndarray) -> dict:
    """Return named portfolio-value percentiles for one forecast month."""
    values = np.percentile(values, [10, 25, 50, 75, 90])
    return dict(zip(("p10", "p25", "p50", "p75", "p90"), map(float, values)))


def _percentile_table(values: np.ndarray, months: int, requested_months, include_fan: bool) -> tuple[dict, list]:
    """Build selected percentiles and, when requested, the complete fan chart."""
    selected = {str(month): _percentile_values(values[:, month]) for month in sorted(set(requested_months)) if 1 <= month <= months}
    fan = [{"month": month, **_percentile_values(values[:, month])} for month in range(1, months + 1)] if include_fan else []
    return selected, fan


def forecast_portfolio(weights, returns, funds, *, start_value, monthly_flow=0.0, months=120, as_of=None, method="improved", block_months=12, paths=10_000, seed=439, real=False, inflation=0.0, parameter_uncertainty=True, keep_ending_values=False, goal=None, yields=None, percentile_months=None, include_fan=True) -> dict:
    """Forecast portfolio values from return history known at the forecast date."""
    frame = _returns_frame(returns)
    if as_of is not None:
        cutoff = pd.Timestamp(as_of).to_period("M").to_timestamp("M")
        frame = frame.loc[:cutoff]
    tickers = [fund.ticker for fund in funds]
    frame = frame[tickers].dropna()
    if frame.empty:
        raise ValueError("Forecasting requires at least one complete monthly return.")
    portfolio_weights = np.asarray(weights, dtype=float)
    rng = np.random.default_rng(seed)
    if method == "simple":
        indices = rng.integers(0, len(frame), size=(paths, months))
        assumptions = _history_assumptions(funds, frame)
    elif method == "improved":
        indices = _block_draws(len(frame), months, block_months, rng, paths)
        assumptions = capital_market_assumptions(funds, frame, frame.index.max(), yields=yields)
    else:
        raise ValueError("method must be simple or improved")
    draws = frame.to_numpy()[indices]
    if method == "improved":
        draws = _mean_adjustment(draws, frame, assumptions, tickers)
        if parameter_uncertainty:
            draws = _parameter_shift(draws, frame, rng)
    portfolio_returns = draws @ portfolio_weights
    if real:
        portfolio_returns = portfolio_returns - inflation / 12
    values = np.empty((paths, months + 1))
    values[:, 0] = start_value
    for month in range(months):
        values[:, month + 1] = values[:, month] * (1 + portfolio_returns[:, month]) + monthly_flow
    requested = percentile_months or (12, 36, 60, months)
    selected, fan = _percentile_table(values, months, requested, include_fan)
    covariance, intensity = shrunk_covariance(frame)
    expected = float(np.dot(portfolio_weights, [assumptions[ticker]["blended"] for ticker in tickers]))
    paid_in = start_value + monthly_flow * months
    peaks = np.maximum.accumulate(values, axis=1)
    yield_dates = next(iter(assumptions.values()))["yield_dates"] if assumptions else {}
    result = {"percentiles": selected, "fan": fan, "probability_losing_money": float(np.mean(values[:, -1] < paid_in)), "probability_20_percent_drawdown": float(np.mean(np.min(values / peaks - 1, axis=1) <= -0.20)), "expected_annual_return": expected, "annual_volatility": float(np.sqrt(portfolio_weights @ covariance @ portfolio_weights)), "assumptions": assumptions, "yield_dates": yield_dates, "shrinkage_intensity": intensity, "method": "Contiguous 12-month historical blocks with forward assumptions" if method == "improved" else "Independent historical months"}
    if goal is not None:
        result["chance_of_goal"] = float(np.mean(values[:, -1] >= goal))
    if keep_ending_values:
        result["ending_values"] = values[:, -1]
    return result


def _calibration_cache_key(weights, frame, methods, horizons, paths, minimum_history) -> str:
    """Create a stable key that changes with settings or the last return month."""
    payload = {"version": 2, "weights": list(np.asarray(weights, dtype=float)), "tickers": list(frame.columns), "methods": list(methods), "horizons": list(horizons), "paths": paths, "minimum_history": minimum_history, "first_month": frame.index[0].date().isoformat(), "last_month": frame.index[-1].date().isoformat()}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def _pinball_loss(values: np.ndarray, low: np.ndarray, middle: np.ndarray, high: np.ndarray) -> float:
    """Measure error for the tenth, fiftieth, and ninetieth percentiles."""
    losses = []
    for quantile, forecast in ((0.1, low), (0.5, middle), (0.9, high)):
        error = values - forecast
        losses.append(np.maximum(quantile * error, (quantile - 1) * error).mean())
    return float(np.mean(losses))


def calibration_test(weights, returns, funds, horizons=(12, 36), methods=("simple", "improved"), minimum_history=60, paths=2000, seed=439) -> dict:
    """Walk forward using only returns and yields known at each forecast month."""
    tickers = [fund.ticker for fund in funds]
    frame = _returns_frame(returns)[tickers].dropna()
    token = _calibration_cache_key(weights, frame, methods, horizons, paths, minimum_history)
    path = Path("data/calibration") / f"{token}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    yields = None
    if "improved" in methods:
        yields = {name: fetch_fred_series(name) for name in FRED_SERIES}
    result = {"methods": {}}
    for method in methods:
        rows_by_horizon = {}
        for horizon in horizons:
            rows = []
            for end in range(minimum_history - 1, len(frame) - horizon):
                history = frame.iloc[:end + 1]
                actual = frame.iloc[end + 1:end + 1 + horizon]
                forecast = forecast_portfolio(weights, history, funds, start_value=1, months=horizon, method=method, paths=paths, seed=seed + end, parameter_uncertainty=(method == "improved"), yields=yields, percentile_months=(horizon,), include_fan=False)
                band = forecast["percentiles"][str(horizon)]
                realized_value = float(np.prod(1 + actual.to_numpy() @ np.asarray(weights)))
                rows.append((history.index[-1].date().isoformat(), band["p10"], band["p50"], band["p90"], realized_value))
            outcomes = np.asarray([row[4] for row in rows])
            low = np.asarray([row[1] for row in rows])
            middle = np.asarray([row[2] for row in rows])
            high = np.asarray([row[3] for row in rows])
            rows_by_horizon[str(horizon)] = {"number_of_forecasts": len(rows), "inside_10_90": float(np.mean((outcomes >= low) & (outcomes <= high))), "below_10": float(np.mean(outcomes < low)), "above_90": float(np.mean(outcomes > high)), "pinball_loss": _pinball_loss(outcomes, low, middle, high), "outcomes": rows}
        result["methods"][method] = rows_by_horizon
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result), encoding="utf-8")
    return result


def _crisis_stock_reference(window, funds) -> pd.Series | None:
    """Return a complete stock reference for one crisis window, if available."""
    if "VT" in window and window["VT"].notna().all():
        return window["VT"]
    stock_tickers = [fund.ticker for fund in funds
                     if fund.role in {"stocks", "individual stock"} and fund.ticker in window
                     and window[fund.ticker].notna().all()]
    return window[stock_tickers].mean(axis=1) if stock_tickers else None


def _crisis_holding_series(fund, window, frame, funds, stock_reference) -> tuple[pd.Series | None, str]:
    """Select one actual or proxy monthly series for a crisis holding."""
    if fund.ticker in window and window[fund.ticker].notna().all():
        return window[fund.ticker], "actual"
    if fund.role == "cash":
        if "SGOV" in window and window["SGOV"].notna().all():
            return window["SGOV"], "proxy"
        bills = fetch_fred_series("TB3MS").reindex(window.index)
        return bills.fillna(0) / 1200, "proxy"
    bond_roles = {"government bonds", "broad bonds", "corporate bonds", "inflation-protected bonds"}
    if fund.role in bond_roles and "IEF" in window:
        return window["IEF"], "proxy"
    if stock_reference is None:
        return None, "unavailable"
    source = frame[fund.ticker] if fund.ticker in frame else stock_reference
    return stock_reference * _beta(source, frame, tuple(funds)), "proxy"


def crisis_scenarios(weights, returns, funds, start_value=10_000) -> list[dict]:
    """Replay crises with identical actual-or-proxy series for all calculations."""
    frame = _returns_frame(returns)
    portfolio_weights = np.asarray(weights, dtype=float)
    scenarios = [("2008 financial crisis", "2008-09", "2009-02"), ("2020 COVID crash", "2020-02", "2020-03"), ("2022 rate shock", "2022-01", "2022-10")]
    results = []
    for name, start, end in scenarios:
        window = frame.loc[start:end]
        holding_series = []
        labels = []
        stock_reference = _crisis_stock_reference(window, funds) if len(window) else None
        for fund in funds:
            series, label = _crisis_holding_series(fund, window, frame, funds, stock_reference)
            holding_series.append(series)
            labels.append(label)
        if not len(window) or any(series is None or series.empty or series.isna().any()
                                  for series in holding_series):
            results.append({"name": name, "period": f"{start} to {end}",
                            "portfolio_return": None, "worst_month": None, "dollars_lost": None,
                            "contributions": {}, "sources": dict(zip([fund.ticker for fund in funds], labels)),
                            "note": "No market data for this period."})
            continue
        holding_returns = [float(np.prod(1 + series) - 1) for series in holding_series]
        contributions = {fund.ticker: float(weight * holding_return) for fund, weight, holding_return in zip(funds, portfolio_weights, holding_returns)}
        monthly_portfolio = np.column_stack([series.to_numpy() for series in holding_series]) @ portfolio_weights
        portfolio_return = float(np.prod(1 + monthly_portfolio) - 1)
        results.append({"name": name, "period": f"{start} to {end}", "portfolio_return": portfolio_return, "worst_month": float(monthly_portfolio.min()), "dollars_lost": float(-portfolio_return * start_value), "contributions": contributions, "sources": dict(zip([fund.ticker for fund in funds], labels))})
    shock = {"stocks": -0.20, "individual stock": -0.20, "government bonds": -0.12, "broad bonds": -0.12, "corporate bonds": -0.15, "inflation-protected bonds": -0.03, "cash": 0.04, "commodities": 0.15, "real estate": -0.18, "other": -0.20}
    holding_returns = np.array([shock[fund.role] for fund in funds])
    portfolio_return = float(portfolio_weights @ holding_returns)
    results.append({"name": "High-inflation year", "period": "hypothetical one-year shock", "portfolio_return": portfolio_return, "worst_month": None, "dollars_lost": -portfolio_return * start_value, "contributions": dict(zip([fund.ticker for fund in funds], portfolio_weights * holding_returns)), "sources": dict.fromkeys([fund.ticker for fund in funds], "hypothetical")})
    return results
