// Formatting and parsing helpers. Every number a person sees goes through one of these.

export const FUNDS = ["SGOV", "IEF", "USIG", "VT"];

export const FUND_INFO = {
  SGOV: { color: "#9AA7B4", name: "SGOV", what: "cash-like Treasury bills" },
  IEF: { color: "#3B82C4", name: "IEF", what: "government bonds" },
  USIG: { color: "#7C5CD6", name: "USIG", what: "corporate bonds" },
  VT: { color: "#00A37A", name: "VT", what: "global stocks" },
};

const EXTRA_COLORS = ["#E07B39", "#D4A017", "#2BB3C0", "#C2417F", "#5E8C31", "#8A6FDF", "#B5651D", "#1F7A8C",
  "#E15759", "#76B7B2", "#59A14F", "#EDC948", "#AF7AA1", "#FF9DA7", "#9C755F"];
const ROLE_WORDS = {
  cash: "cash", "government bonds": "government bonds", "broad bonds": "broad bonds",
  "corporate bonds": "corporate bonds", "inflation-protected bonds": "inflation-protected bonds",
  stocks: "stock fund", "individual stock": "individual stock", "real estate": "real estate",
  commodities: "commodities", other: "other",
};
const fundRegistry = {};

/** Remember names and roles of funds the service has described, so every page can label them. */
export function registerFunds(funds = []) {
  for (const fund of funds) {
    if (fund?.ticker) fundRegistry[fund.ticker] = { ...fundRegistry[fund.ticker], ...fund };
  }
}

/** The tickers in a weights object, in a stable order: the four default funds first. */
export function tickersOf(weights) {
  const keys = Object.keys(weights ?? {});
  return [...FUNDS.filter((fund) => keys.includes(fund)), ...keys.filter((key) => !FUNDS.includes(key))];
}

export function fundColor(ticker) {
  if (FUND_INFO[ticker]) return FUND_INFO[ticker].color;
  let hash = 0;
  for (const character of String(ticker)) hash = (hash * 31 + character.charCodeAt(0)) % 997;
  return EXTRA_COLORS[hash % EXTRA_COLORS.length];
}

export function fundWhat(ticker) {
  if (FUND_INFO[ticker]) return FUND_INFO[ticker].what;
  const known = fundRegistry[ticker];
  if (!known) return "";
  const name = known.name && known.name !== ticker ? known.name : "";
  const role = ROLE_WORDS[known.role] ?? known.role ?? "";
  return [name, role].filter(Boolean).join(", ");
}

export const PORTFOLIO_COLORS = {
  "Your plan": "#00A37A",
  "Constrained portfolio": "#00A37A",
  "60/40 benchmark": "#D99A00",
  "Equal weight": "#7A8797",
};

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
  "October", "November", "December"];

/** Turn what a person typed ("$1,000,000", "1.2k is not supported") into a plain number. */
export function parseMoney(text) {
  const cleaned = String(text ?? "").replace(/[^0-9.]/g, "");
  const value = Number.parseFloat(cleaned);
  return Number.isFinite(value) ? value : 0;
}

/** $1,234,567 (no cents unless asked). */
export function money(value, cents = false) {
  if (value === null || value === undefined || Number.isNaN(value)) return "not known";
  const digits = cents ? 2 : 0;
  const sign = value < 0 ? "-" : "";
  return `${sign}$${Math.abs(value).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
}

/** Headline style: $134.3 million, $1.2 billion, or $438,012 below one million. */
export function moneyShort(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "not known";
  const size = Math.abs(value);
  if (size >= 1e9) return `$${(value / 1e9).toFixed(2)} billion`;
  if (size >= 1e6) return `$${(value / 1e6).toFixed(1)} million`;
  return money(value);
}

/** 0.0735 -> 7.35% */
export function percent(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return "not known";
  return `${(value * 100).toFixed(digits)}%`;
}

/** 0.15 -> 15% with no decimals unless needed. */
export function weight(value) {
  if (value === null || value === undefined) return "not known";
  const scaled = value * 100;
  return `${Number.isInteger(Math.round(scaled * 100) / 100) ? Math.round(scaled) : scaled.toFixed(1)}%`;
}

/** 0.25 weight change -> "25 points" */
export function points(value) {
  if (value === null || value === undefined) return "no mix";
  return `${Math.round(value * 100)} points`;
}

export function count(value) {
  return Number(value).toLocaleString("en-US");
}

/** "2026-08-01" -> "August 2026" */
export function monthName(text) {
  const match = /^(\d{4})-(\d{2})/.exec(String(text ?? ""));
  if (!match) return String(text ?? "");
  return `${MONTHS[Number(match[2]) - 1]} ${match[1]}`;
}

/** "2026-09-11" -> "September 11, 2026" */
export function dateLong(text) {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(text ?? ""));
  if (!match) return String(text ?? "");
  return `${MONTHS[Number(match[2]) - 1]} ${Number(match[3])}, ${match[1]}`;
}

export function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, (character) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character]));
}

/** "SGOV 0% · IEF 15% · USIG 15% · VT 70%" */
export function mixText(weights) {
  if (!weights) return "No mix meets the rules";
  return tickersOf(weights).filter((fund) => weights[fund] > 0.0001).map((fund) => `${fund} ${weight(weights[fund])}`).join(" · ");
}

/** One mandate verdict as a plain sentence. */
export function verdictSentence(verdict) {
  const rule = String(verdict.rule ?? "");
  const measured = verdict.measured_value;
  const limit = verdict.limit;
  const ok = Boolean(verdict.pass);
  const lower = rule.toLowerCase();
  if (lower.startsWith("long-only")) {
    return ok ? "No fund is held short" : `A fund is held short (${weight(measured)})`;
  }
  if (lower.startsWith("weights sum")) {
    return ok ? "Weights add up to 100%" : `Weights add up to ${weight(measured)}, not 100%`;
  }
  if (lower.includes("sgov + ief") || lower.includes("reserve")) {
    return ok
      ? `Reserve in SGOV and IEF is ${weight(measured)}, at least ${weight(limit)}`
      : `Reserve in SGOV and IEF is ${weight(measured)}, below the ${weight(limit)} minimum`;
  }
  if (lower.startsWith("no fund above")) {
    return ok
      ? `Largest fund is ${weight(measured)}, within the ${weight(limit)} cap`
      : `Largest fund is ${weight(measured)}, above the ${weight(limit)} cap`;
  }
  if (lower.includes("return at least") || lower.includes("expected return")) {
    return ok
      ? `Expected return ${percent(measured)} meets the ${percent(limit)} objective`
      : `Expected return ${percent(measured)} is below the ${percent(limit)} objective`;
  }
  if (lower.includes("single") || lower.includes("one individual stock") || lower.includes("any individual stock")) {
    return ok
      ? `Largest single stock is ${weight(measured)}, within the ${weight(limit)} limit`
      : `Largest single stock is ${weight(measured)}, above the ${weight(limit)} limit`;
  }
  if (lower.includes("individual stocks") || lower.includes("stocks total") || lower.includes("combined")) {
    return ok
      ? `Individual stocks total ${weight(measured)}, within the ${weight(limit)} limit`
      : `Individual stocks total ${weight(measured)}, above the ${weight(limit)} limit`;
  }
  if (lower.includes("holdings")) {
    return ok
      ? `${measured} holdings of at least 2%, meeting the minimum of ${limit}`
      : `Only ${measured} holdings of at least 2%, below the minimum of ${limit}`;
  }
  if (lower.includes("12-month")) {
    return ok
      ? `Worst 12-month return ${percent(measured)} is within the ${weight(limit)} limit`
      : `Worst 12-month return ${percent(measured)} is beyond the ${weight(limit)} limit`;
  }
  return `${rule}${ok ? "" : " (not met)"}`;
}

/** Plain-English meanings for finance words. Hover or tap a dotted word to read one. */
export const GLOSSARY = {
  "Volatility": "How much the value swings from year to year. 10% means a typical year lands within about 10 points of the average.",
  "Expected return": "The average yearly return the model expects. Real years will be higher or lower.",
  "Sharpe ratio": "Return earned above cash for each unit of risk taken. Higher is better; above 0.5 is decent for a portfolio.",
  "Sortino ratio": "Like the Sharpe ratio, but only counts downside swings as risk. Higher is better.",
  "Beta": "How much the portfolio moves when global stocks move. 1.0 moves with the market; 0.5 moves about half as much.",
  "Largest drop": "The biggest fall from a high point to a low point before recovering (also called maximum drawdown).",
  "Percentile": "The 10th percentile is a poor outcome: only 1 in 10 simulated futures did worse. The 90th is a strong one.",
  "Median": "The middle outcome: half of the simulated futures did better, half did worse.",
  "Share of risk": "How much of the portfolio's ups and downs come from each holding. A small holding can carry a big share of risk.",
  "Correlation": "Whether two holdings move together (near 1), independently (near 0), or opposite (below 0).",
  "Expense ratio": "The yearly fee a fund charges, taken from its value. 0.10% costs $10 a year on $10,000.",
  "Calibration": "Whether the forecast ranges were honest in the past. An 80% range should contain about 80% of real outcomes.",
  "Diversification ratio": "Above 1 means holdings partly cancel each other's swings, so the whole is steadier than its parts.",
  "Risk score": "A 1-to-10 summary of how bumpy the ride is, based on volatility. 1 is like cash; 10 is like a single stock.",
  "Emergency reserve": "Cash set aside for surprise bills before investing, so you never have to sell in a downturn.",
  "Real return": "Return after inflation, so it measures what your money can actually buy.",
  "Stop condition": "A safety check: if small changes to the inputs flip the recommended mix, the plan is not stable enough to trust.",
  "13F filing": "A report large investment managers file with the SEC every quarter listing the U.S. stocks they own.",
};

/** Wrap a word so it shows its plain-English meaning on hover, focus or tap. */
export function term(word, label = word) {
  const meaning = GLOSSARY[word];
  if (!meaning) return escapeHtml(label);
  return `<span class="term" tabindex="0" data-tip="${escapeHtml(meaning)}">${escapeHtml(label)}</span>`;
}
