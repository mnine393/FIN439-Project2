"""Fund-universe records, validation, and role-based portfolio defaults."""
from __future__ import annotations

from dataclasses import dataclass
import re


ROLES = (
    "cash", "government bonds", "broad bonds", "corporate bonds",
    "inflation-protected bonds", "stocks", "individual stock", "real estate", "commodities", "other",
)

ROLE_TABLE = {
    "cash": {"SGOV", "BIL", "SHV", "USFR", "TFLO"},
    "government bonds": {"IEF", "TLT", "GOVT", "SHY", "IEI", "VGIT", "VGLT"},
    "broad bonds": {"BND", "AGG"},
    "corporate bonds": {"USIG", "LQD", "VCIT", "IGIB"},
    "inflation-protected bonds": {"SCHP", "TIP", "VTIP", "STIP"},
    "stocks": {"VT", "VTI", "VOO", "SPY", "IVV", "QQQ", "VXUS", "VEA", "VWO", "IWM", "SCHD", "VUG", "VTV", "EFA", "EEM"},
    "real estate": {"VNQ", "VNQI", "SCHH"},
    "commodities": {"GLD", "IAU", "DBC", "PDBC", "SLV"},
}


@dataclass(frozen=True)
class Fund:
    """A tradable fund and the role used by Compass portfolio rules."""

    ticker: str
    name: str = ""
    role: str = "other"
    reserve_eligible: bool = False


def guessed_role(ticker: str) -> str:
    """Return the built-in role guess for a normalized ticker."""
    return next((role for role, tickers in ROLE_TABLE.items() if ticker in tickers), "other")


def normalize_ticker(ticker: str) -> str:
    """Upper-case and validate a Yahoo Finance ticker."""
    value = ticker.strip().upper()
    if not value or not re.fullmatch(r"[A-Z0-9.-]+", value):
        raise ValueError(f"Ticker '{ticker}' must use only letters, digits, dots, and hyphens.")
    return value


def make_funds(items) -> tuple[Fund, ...]:
    """Build a validated two-to-fifteen holding universe from ticker records."""
    funds = []
    for item in items:
        source = item if isinstance(item, dict) else {"ticker": item}
        ticker = normalize_ticker(source["ticker"])
        role = source.get("role") or guessed_role(ticker)
        if role not in ROLES:
            raise ValueError(f"Role for {ticker} must be one of: {', '.join(ROLES)}.")
        reserve = source.get("reserve_eligible")
        if reserve is None:
            reserve = role in ("cash", "government bonds")
        funds.append(Fund(ticker, source.get("name", ""), role, bool(reserve)))
    if not 2 <= len(funds) <= 15:
        raise ValueError("A universe must contain from 2 to 15 tickers.")
    if len({fund.ticker for fund in funds}) != len(funds):
        raise ValueError("A universe cannot contain the same ticker more than once.")
    return tuple(funds)


DEFAULT_UNIVERSE = (
    Fund("SGOV", "", "cash", True),
    Fund("IEF", "", "government bonds", True),
    Fund("USIG", "", "corporate bonds", False),
    Fund("VT", "", "stocks", False),
)


def is_default(funds: tuple[Fund, ...]) -> bool:
    """Return whether funds are the untouched default universe."""
    return funds == DEFAULT_UNIVERSE


def benchmark_weights(funds: tuple[Fund, ...]) -> tuple[float, ...]:
    """Create the documented role-based benchmark for a universe."""
    tickers = [fund.ticker for fund in funds]
    if "VT" in tickers and "IEF" in tickers:
        return tuple(.60 if fund.ticker == "VT" else .40 if fund.ticker == "IEF" else 0.0 for fund in funds)
    stock = [index for index, fund in enumerate(funds)
             if fund.role in {"stocks", "individual stock"}]
    bonds = [index for index, fund in enumerate(funds) if fund.role in {
        "government bonds", "broad bonds", "corporate bonds", "inflation-protected bonds"
    }]
    cash = [index for index, fund in enumerate(funds) if fund.role == "cash"]
    weights = [0.0] * len(funds)
    def add(indexes, amount):
        if indexes:
            for index in indexes:
                weights[index] += amount / len(indexes)
            return True
        return False
    stock_target = stock or cash or bonds
    bond_target = bonds or cash or stock
    add(stock_target, .60)
    add(bond_target, .40)
    return tuple(weights)
