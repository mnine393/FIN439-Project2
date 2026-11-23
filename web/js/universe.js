// The fund and stock picker shared by both modes. A universe is a list of {ticker, name, role, reserve_eligible}.
import { lookupTicker, refreshPrices } from "./api.js";
import { escapeHtml, fundColor, registerFunds } from "./format.js";

export const MAX_HOLDINGS = 15;

export const ROLES = [
  "cash", "government bonds", "broad bonds", "corporate bonds", "inflation-protected bonds", "stocks",
  "individual stock", "real estate", "commodities", "other",
];

export const DEFAULT_UNIVERSE = [
  { ticker: "SGOV", name: "iShares 0-3 Month Treasury Bond ETF", role: "cash", reserve_eligible: true },
  { ticker: "IEF", name: "iShares 7-10 Year Treasury Bond ETF", role: "government bonds", reserve_eligible: true },
  { ticker: "USIG", name: "iShares Broad USD Investment Grade Corporate Bond ETF", role: "corporate bonds", reserve_eligible: false },
  { ticker: "VT", name: "Vanguard Total World Stock ETF", role: "stocks", reserve_eligible: false },
];

export const PRESETS = {
  "The four core funds (graded default)": DEFAULT_UNIVERSE.map((fund) => fund.ticker),
  "Diversified funds": ["SGOV", "IEF", "SCHP", "USIG", "VTI", "VXUS", "VNQ", "GLD"],
  "Funds plus a few quality stocks": ["SGOV", "IEF", "USIG", "VT", "AAPL", "KO", "AXP", "COST"],
};

registerFunds(DEFAULT_UNIVERSE);

export function isDefaultUniverse(universe) {
  if (!universe || universe.length !== DEFAULT_UNIVERSE.length) return !universe;
  return DEFAULT_UNIVERSE.every((fund, index) => (
    universe[index].ticker === fund.ticker && universe[index].role === fund.role
    && Boolean(universe[index].reserve_eligible) === fund.reserve_eligible));
}

/** What the service expects: nothing for the default, otherwise the trimmed list. */
export function universeForRequest(universe) {
  if (isDefaultUniverse(universe)) return undefined;
  return universe.map(({ ticker, role, reserve_eligible }) => ({ ticker, role, reserve_eligible: Boolean(reserve_eligible) }));
}

/** Query parameters for the institution endpoint. */
export function universeQuery(universe) {
  if (isDefaultUniverse(universe)) return {};
  return {
    tickers: universe.map((fund) => fund.ticker).join(","),
    reserve: universe.filter((fund) => fund.reserve_eligible).map((fund) => fund.ticker).join(","),
    roles: universe.map((fund) => `${fund.ticker}:${fund.role}`).join(","),
  };
}

function row(fund, index) {
  const options = ROLES.map((role) => `<option ${role === fund.role ? "selected" : ""}>${role}</option>`).join("");
  return `<div class="fund-row" data-index="${index}">
    <span class="dot" style="background:${fundColor(fund.ticker)}"></span>
    <div class="fund-name"><strong>${escapeHtml(fund.ticker)}</strong>
      <span class="muted">${escapeHtml(fund.name && fund.name !== fund.ticker ? fund.name : "")}</span>
      ${fund.first_month ? `<span class="muted fund-history">history from ${escapeHtml(String(fund.first_month).slice(0, 7))}</span>` : ""}</div>
    <select class="input fund-role" data-role="${index}" aria-label="Role of ${escapeHtml(fund.ticker)}">${options}</select>
    <label class="fund-reserve"><input type="checkbox" data-reserve="${index}" ${fund.reserve_eligible ? "checked" : ""}> reserve</label>
    <button class="button ghost small" type="button" data-remove="${index}" aria-label="Remove ${escapeHtml(fund.ticker)}">✕</button>
  </div>`;
}

/**
 * Render an editable universe into `container`. `state.universe` is updated in place; `onChange` runs after
 * every change.
 */
export function renderUniverseEditor(container, state, onChange = () => {}) {
  const presets = Object.keys(PRESETS).map((name) => `<option>${escapeHtml(name)}</option>`).join("");
  const draw = (message = "") => {
    const universe = state.universe;
    container.innerHTML = `<div class="stack">
      <div class="fund-list">${universe.map(row).join("")}</div>
      <div class="fund-add">
        <input class="input" data-new-ticker placeholder="Add any ticker, for example AAPL or VNQ" maxlength="12"
          ${universe.length >= MAX_HOLDINGS ? "disabled" : ""}>
        <button class="button small" type="button" data-add ${universe.length >= MAX_HOLDINGS ? "disabled" : ""}>Add</button>
      </div>
      <div class="fund-tools">
        <select class="input" data-preset aria-label="Start from a preset"><option value="">Start from a preset…</option>${presets}</select>
        <button class="button ghost small" type="button" data-refresh>Refresh prices from Yahoo Finance</button>
      </div>
      <p class="caption">${universe.length} of ${MAX_HOLDINGS} holdings. "Reserve" marks what counts toward the cash
        reserve rule. Prices come from Yahoo Finance and are saved, so plans still run offline.</p>
      <div data-universe-message>${message}</div>
    </div>`;
    wire();
  };
  const note = (kind, text) => `<div class="banner ${kind}"><span>${kind === "bad" ? "✕" : "i"}</span><span>${escapeHtml(text)}</span></div>`;
  const add = async (ticker) => {
    const symbol = ticker.trim().toUpperCase();
    if (!symbol) return;
    if (state.universe.some((fund) => fund.ticker === symbol)) { draw(note("info", `${symbol} is already in the list.`)); return; }
    if (state.universe.length >= MAX_HOLDINGS) { draw(note("bad", `The limit is ${MAX_HOLDINGS} holdings.`)); return; }
    draw(note("info", `Looking up ${symbol} on Yahoo Finance...`));
    try {
      const fund = await lookupTicker(symbol);
      registerFunds([fund]);
      state.universe.push({ ticker: fund.ticker, name: fund.name, role: fund.role, reserve_eligible: Boolean(fund.reserve_eligible), first_month: fund.first_month });
      draw();
      onChange();
    } catch (error) {
      draw(note("bad", `Could not add ${symbol}: ${error.message.includes("404") ? "Yahoo Finance does not know this ticker." : error.message}`));
    }
  };
  const wire = () => {
    const input = container.querySelector("[data-new-ticker]");
    container.querySelector("[data-add]")?.addEventListener("click", () => add(input.value));
    input?.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); add(input.value); } });
    container.querySelectorAll("[data-remove]").forEach((button) => button.addEventListener("click", () => {
      if (state.universe.length <= 2) { draw(note("bad", "A plan needs at least two holdings.")); return; }
      state.universe.splice(Number(button.dataset.remove), 1);
      draw();
      onChange();
    }));
    container.querySelectorAll("[data-role]").forEach((select) => select.addEventListener("change", () => {
      state.universe[Number(select.dataset.role)].role = select.value;
      onChange();
    }));
    container.querySelectorAll("[data-reserve]").forEach((box) => box.addEventListener("change", () => {
      state.universe[Number(box.dataset.reserve)].reserve_eligible = box.checked;
      onChange();
    }));
    container.querySelector("[data-preset]").addEventListener("change", async (event) => {
      const tickers = PRESETS[event.target.value];
      if (!tickers) return;
      if (event.target.value.startsWith("The four core funds")) {
        state.universe = DEFAULT_UNIVERSE.map((fund) => ({ ...fund }));
        draw();
        onChange();
        return;
      }
      state.universe = [];
      for (const ticker of tickers) {
        await add(ticker);
      }
    });
    container.querySelector("[data-refresh]").addEventListener("click", async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      button.innerHTML = `<span class="spinner" style="border-color:rgba(11,31,58,.25);border-top-color:#0B1F3A"></span>Refreshing...`;
      try {
        await refreshPrices(state.universe.map((fund) => fund.ticker));
        draw(note("info", "Prices refreshed from Yahoo Finance. Build the plan again to use them."));
      } catch (error) {
        draw(note("bad", `Refresh failed: ${error.message}. The saved prices are still used.`));
      }
    });
  };
  draw();
}
