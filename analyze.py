"""Portfolio diagnostics built on the forecast engine."""
from __future__ import annotations

import numpy as np
import pandas as pd

from forecast import crisis_scenarios, fetch_fred_series, forecast_portfolio, shrunk_covariance

EXPENSE_RATIOS = {
    "SGOV": 0.0009, "BIL": 0.00135, "IEF": 0.0015, "TLT": 0.0015,
    "BND": 0.0003, "AGG": 0.0003, "USIG": 0.0004, "LQD": 0.0014,
    "TIP": 0.0019, "SCHP": 0.0003, "VT": 0.0007, "VTI": 0.0003,
    "VOO": 0.0003, "SPY": 0.000945, "IVV": 0.0003, "VNQ": 0.0013,
    "GLD": 0.004, "IAU": 0.0025,
}


def _frame(returns, tickers, as_of):
    """Standardize the monthly return history used for a portfolio analysis."""
    frame = returns.copy()
    if "month" in frame:
        frame = frame.set_index("month")
    frame.index = pd.to_datetime(frame.index).to_period("M").to_timestamp("M")
    if as_of is not None:
        cutoff = pd.Timestamp(as_of).to_period("M").to_timestamp("M")
        frame = frame.loc[:cutoff]
    return frame[tickers].sort_index()


def _crisis_frame(returns, as_of):
    """Keep all available return columns for historical crisis proxies."""
    frame = returns.copy()
    if "month" in frame:
        frame = frame.set_index("month")
    frame.index = pd.to_datetime(frame.index).to_period("M").to_timestamp("M")
    if as_of is not None:
        frame = frame.loc[:pd.Timestamp(as_of).to_period("M").to_timestamp("M")]
    return frame.sort_index()


def _risk_free_rate(frame: pd.DataFrame) -> tuple[pd.Series, str]:
    """Use the invested cash proxy before falling back to Treasury bill yields."""
    if "SGOV" in frame:
        return frame["SGOV"].fillna(0), "SGOV monthly return"
    bills = fetch_fred_series("TB3MS").reindex(frame.index)
    if bills.notna().any():
        return bills.fillna(0) / 1200, "TB3MS divided by 1200"
    return pd.Series(0.0, index=frame.index), "0 because no cash or Treasury bill data were available"


def history_statistics(frame, weights, funds) -> dict:
    """Calculate return, downside risk, beta, and risk-adjusted history measures."""
    portfolio = frame.to_numpy() @ weights
    portfolio_series = pd.Series(portfolio, index=frame.index)
    risk_free, source = _risk_free_rate(frame)
    excess = portfolio_series - risk_free
    volatility = float(portfolio_series.std(ddof=1) * np.sqrt(12))
    downside = np.sqrt(np.mean(np.minimum(excess, 0) ** 2))
    stock_tickers = [fund.ticker for fund in funds if fund.role in {"stocks", "individual stock"}]
    equity = frame["VT"] if "VT" in frame else frame[stock_tickers].mean(axis=1)
    beta = 1.0 if equity.var() == 0 else float(portfolio_series.cov(equity) / equity.var())
    rolling = portfolio_series.rolling(12).apply(lambda values: np.prod(1 + values) - 1, raw=True)
    return {
        "annual_return": float(portfolio_series.mean() * 12),
        "volatility": volatility,
        "sharpe_ratio": float(excess.mean() / portfolio_series.std(ddof=1) * np.sqrt(12)) if volatility else 0.0,
        "sortino_ratio": float(excess.mean() / downside * np.sqrt(12)) if downside else None,
        "best_12_months": float(rolling.max()),
        "worst_12_months": float(rolling.min()),
        "beta": beta,
        "risk_free_rate_source": source,
    }


def risk_contributions(covariance, weights, tickers) -> dict:
    """Allocate total variance by holding and normalize contributions to 100 percent."""
    variance = float(weights @ covariance @ weights)
    if variance <= 0:
        shares = np.zeros(len(weights))
    else:
        shares = weights * (covariance @ weights) / variance
    percentages = shares * 100
    return dict(zip(tickers, map(float, percentages)))


def correlation_table(covariance, tickers, shrinkage) -> dict:
    """Return a readable rounded correlation matrix and its shrinkage intensity."""
    standard_deviations = np.sqrt(np.diag(covariance))
    correlation = covariance / np.outer(standard_deviations, standard_deviations)
    return {
        "tickers": tickers,
        "matrix": np.round(correlation, 3).tolist(),
        "shrinkage_intensity": float(shrinkage),
    }


def drawdown_and_growth(frame, weights) -> tuple[dict, list, list]:
    """Find the peak immediately before the deepest trough and build chart series."""
    portfolio = frame.to_numpy() @ weights
    growth = 10_000 * np.cumprod(1 + portfolio)
    peaks = np.maximum.accumulate(growth)
    drawdown = growth / peaks - 1
    trough_position = int(np.argmin(drawdown))
    peak_position = int(np.argmax(growth[:trough_position + 1]))
    summary = {
        "maximum_drawdown": float(drawdown[trough_position]),
        "maximum_drawdown_start": frame.index[peak_position].date().isoformat(),
        "maximum_drawdown_end": frame.index[trough_position].date().isoformat(),
    }
    drawdown_series = [
        {"month": date.date().isoformat(), "drawdown": float(value)}
        for date, value in zip(frame.index, drawdown)
    ]
    growth_series = [
        {"month": date.date().isoformat(), "value": float(value)}
        for date, value in zip(frame.index, growth)
    ]
    return summary, drawdown_series, growth_series


def risk_score(volatility) -> dict:
    """Convert annual volatility into the course's one-to-ten risk scale."""
    score = int(round(np.clip(1 + 9 * (volatility - 0.02) / 0.23, 1, 10)))
    return {"score": score, "meaning": f"Risk score {score} of 10 based on {volatility:.1%} annual volatility."}


def concentration(weights, tickers) -> dict:
    """Summarize position concentration from portfolio weights."""
    return {
        "largest_holding_weight": float(weights.max()),
        "top_3_weight": float(np.sort(weights)[-3:].sum()),
        "number_of_holdings": len(tickers),
        "effective_number_of_holdings": float(1 / np.sum(weights ** 2)),
    }


def fee_summary(weights, tickers, total) -> dict:
    """Calculate known sponsor expense ratios and annual dollar cost."""
    fees = [EXPENSE_RATIOS.get(ticker) for ticker in tickers]
    known_fee = None
    if all(fee is not None for fee in fees):
        known_fee = sum(weight * fee for weight, fee in zip(weights, fees))
    by_holding = {ticker: fee if fee is not None else "not known" for ticker, fee in zip(tickers, fees)}
    return {
        "by_holding": by_holding,
        "source": "fund sponsor published expense ratio, saved table",
        "weighted_portfolio_fee": known_fee,
        "dollars_per_year": None if known_fee is None else total * known_fee,
    }


def warning_flags(weights, roles, fees, score, history_months) -> list[str]:
    """Flag concentration, allocation, cost, and short-history finance concerns."""
    flags = []
    if weights.max() > 0.40:
        flags.append("One holding is more than 40% of the portfolio.")
    if roles.get("stocks", 0) + roles.get("individual stock", 0) > 0.90:
        flags.append("Stocks are more than 90% of the portfolio.")
    bond_roles = ("cash", "government bonds", "broad bonds", "corporate bonds", "inflation-protected bonds")
    if sum(roles.get(role, 0) for role in bond_roles) == 0:
        flags.append("The portfolio has no bonds or cash.")
    if fees["weighted_portfolio_fee"] is not None and fees["weighted_portfolio_fee"] > 0.005:
        flags.append("The weighted annual fee is over 0.5%.")
    if score["score"] >= 9:
        flags.append("The risk score is very high.")
    if history_months < 60:
        flags.append("Under five years of history shortens the analysis window.")
    return flags


def analyze_portfolio(holdings: dict[str, float], funds, returns, *, crisis_returns=None,
                      horizon_years=10, monthly_flow=0.0, as_of=None) -> dict:
    """Return history, concentration, costs, stress, and two forecasts for holdings."""
    tickers = [fund.ticker for fund in funds]
    total = float(sum(holdings.values()))
    if total <= 0:
        raise ValueError("Holdings must total more than zero.")
    weights = np.array([holdings.get(ticker, 0.0) / total for ticker in tickers])
    frame = _frame(returns, tickers, as_of).dropna()
    covariance, shrinkage = shrunk_covariance(frame)
    history = history_statistics(frame, weights, funds)
    drawdown, drawdown_series, growth_series = drawdown_and_growth(frame, weights)
    history.update(drawdown)
    roles = {role: float(sum(weight for weight, fund in zip(weights, funds) if fund.role == role)) for role in {fund.role for fund in funds}}
    score = risk_score(history["volatility"])
    fees = fee_summary(weights, tickers, total)
    months = horizon_years * 12
    return {
        "weights": dict(zip(tickers, weights)),
        "total_value": total,
        "allocation_by_role": roles,
        "history": history,
        "risk_contribution": risk_contributions(covariance, weights, tickers),
        "diversification_ratio": float((weights @ np.sqrt(np.diag(covariance))) / np.sqrt(weights @ covariance @ weights)),
        "correlation": correlation_table(covariance, tickers, shrinkage),
        "drawdown_series": drawdown_series,
        "growth_of_10000": growth_series,
        "risk_score": score,
        "concentration": concentration(weights, tickers),
        "fees": fees,
        "forecast": {
            "improved": forecast_portfolio(weights, frame, funds, start_value=total, monthly_flow=monthly_flow, months=months, method="improved"),
            "simple": forecast_portfolio(weights, frame, funds, start_value=total, monthly_flow=monthly_flow, months=months, method="simple"),
        },
        "crisis_scenarios": crisis_scenarios(
            weights, _crisis_frame(crisis_returns if crisis_returns is not None else returns, as_of), funds, total),
        "flags": warning_flags(weights, roles, fees, score, len(frame)),
    }


def _comparison_headline(item: dict) -> dict:
    """Extract the comparable headline fields from a full analysis."""
    return {"total_value": item["total_value"], "annual_return": item["history"]["annual_return"], "volatility": item["history"]["volatility"], "risk_score": item["risk_score"]["score"], "weighted_fee": item["fees"]["weighted_portfolio_fee"]}


def compare_portfolios(a_holdings, b_holdings, funds, returns, **kwargs):
    """Compare headline figures for two holding dictionaries."""
    a = analyze_portfolio(a_holdings, funds, returns, **kwargs)
    b = analyze_portfolio(b_holdings, funds, returns, **kwargs)
    a_headline = _comparison_headline(a)
    b_headline = _comparison_headline(b)
    differences = {key: None if a_headline[key] is None or b_headline[key] is None else a_headline[key] - b_headline[key] for key in a_headline}
    return {"a": a_headline, "b": b_headline, "differences": differences, "details": {"a": a, "b": b}}


QUESTIONS = [{"key": "time_horizon", "question": "How long until you need the money?", "labels": ["Under 2 years", "2 to 5 years", "5 to 10 years", "10 to 20 years", "Over 20 years"]}, {"key": "reaction", "question": "After a 20% drop, what would you do?", "labels": ["Sell all", "Sell some", "Hold", "Buy some", "Buy more"]}, {"key": "income_stability", "question": "How stable is your income?", "labels": ["Very unstable", "Unstable", "Moderate", "Stable", "Very stable"]}, {"key": "experience", "question": "What is your investing experience?", "labels": ["None", "Limited", "Some", "Experienced", "Very experienced"]}, {"key": "priority", "question": "What is your main goal?", "labels": ["Protect money", "Mostly protect", "Balance", "Mostly grow", "Grow as much as possible"]}]


def risk_profile(answers: dict) -> dict:
    """Score five one-to-five answers and suggest a stock allocation."""
    values = [int(answers.get(question["key"], 3)) for question in QUESTIONS]
    if any(value < 1 or value > 5 for value in values):
        raise ValueError("Risk-profile answers must be from 1 through 5.")
    score = round(1 + 9 * (sum(values) - 5) / 20)
    return {"score": score, "suggested_stock_share": min(0.95, 0.10 + 0.09 * (score - 1)), "questions": QUESTIONS, "answers": dict(zip([question["key"] for question in QUESTIONS], values))}
