// Legends: what Warren Buffett and Michael Burry actually own, from their SEC 13F filings.
import { getLegend } from "./api.js";
import { dateLong, escapeHtml, money, moneyShort, percent, registerFunds, weight } from "./format.js";
import { loadInputs, saveInputs } from "./personal.js";
import { screensHtml } from "./screens.js";
import { DEFAULT_UNIVERSE } from "./universe.js";
import { openInAnalyze } from "./analyze.js";
import { setAssistantContext } from "./assistant.js";
import { chip, errorCard, metricCard, skeleton, table, verdictChips } from "./ui.js";

const KEYS = ["buffett", "burry"];
const PEOPLE = {
  buffett: { person: "Warren Buffett", firm: "Berkshire Hathaway", style: "Concentrated, long-term owner of high-quality businesses." },
  burry: { person: "Michael Burry", firm: "Scion Asset Management", style: "Contrarian deep-value investor who also bets against stocks with put options." },
};

function asList(body) {
  if (Array.isArray(body)) return body;
  if (Array.isArray(body?.legends)) return body.legends;
  return KEYS.map((key) => (body?.[key] ? { key, ...body[key] } : null)).filter(Boolean);
}

function keyOf(summary, index) {
  if (summary.key) return summary.key;
  const text = `${summary.filer ?? ""} ${summary.person ?? ""}`.toLowerCase();
  return text.includes("burry") || text.includes("scion") ? "burry" : text.includes("buffett") || text.includes("berkshire") ? "buffett" : KEYS[index];
}

function staleBanner(summary) {
  if (!summary.stale) return "";
  return `<div class="banner caution"><span>!</span><span>Old filing.
    <span class="detail">${escapeHtml(summary.stale_message ?? "The latest 13F filing is more than 200 days old.")}</span></span></div>`;
}

function legendCard(summary, key) {
  const who = PEOPLE[key];
  const largest = summary.largest_holding;
  return `<a class="card stack" href="#/legends/${key}" style="text-decoration:none;color:inherit">
    <p class="group-title">${escapeHtml(who.firm)}</p>
    <h2>${escapeHtml(who.person)}</h2>
    <p class="muted">${escapeHtml(who.style)}</p>
    <div class="kv"><span>Holdings report for</span><span>${escapeHtml(dateLong(summary.report_period))}</span></div>
    <div class="kv"><span>Filed with the SEC</span><span>${escapeHtml(dateLong(summary.filing_date))} (${summary.days_to_file} days later)</span></div>
    <div class="kv"><span>Stocks held</span><span>${summary.number_of_stock_holdings}</span></div>
    <div class="kv"><span>Share in the top 5</span><span>${percent(summary.top_5_weight, 0)}</span></div>
    ${largest ? `<div class="kv"><span>Largest holding</span><span>${escapeHtml(largest.ticker ?? largest.issuer)} ${weight(largest.weight)}</span></div>` : ""}
    ${staleBanner(summary)}
    <span class="button small" style="align-self:flex-start">See the portfolio →</span>
  </a>`;
}

export async function renderLegendsHome(root) {
  root.innerHTML = `<div class="page">
    <span class="eyebrow" style="display:inline-block;background:var(--accent-soft);color:var(--accent-dark);font-weight:700;font-size:13px;padding:5px 12px;border-radius:999px">Legends</span>
    <h1 style="margin-top:14px">What the legends actually own</h1>
    <p class="lede muted" style="font-size:18px;margin-top:12px;max-width:760px">Large investment firms must report their
      stock holdings to the SEC every quarter in a 13F filing, about 45 days after the quarter ends. Compass reads those
      filings directly, uses only what was filed by the decision date, and lets you build a plan from them.</p>
    <div id="legends-body" style="margin-top:28px">${skeleton("Reading the latest 13F filings from SEC EDGAR...", 260)}</div>
  </div>`;
  const body = root.querySelector("#legends-body");
  try {
    const list = asList(await getLegend("/api/legends"));
    body.innerHTML = `<div class="legend-hero">${list.map((summary, index) => legendCard(summary, keyOf(summary, index))).join("")}</div>
      <div class="card" style="margin-top:18px"><p><strong>Why the date matters.</strong> A 13F shows what a firm held on
      the last day of a quarter, but nobody could see it until the filing date. Copying a legend's "current" portfolio
      always means copying it about six weeks late, and sometimes much later.</p></div>`;
  } catch (error) {
    body.innerHTML = errorCard(error.message);
  }
}

function holdingsTable(holdings) {
  const top = Math.max(...holdings.map((holding) => holding.weight ?? 0), 0.0001);
  const rows = holdings.map((holding) => [
    `<strong>${escapeHtml(holding.ticker ?? "—")}</strong>`,
    escapeHtml(holding.issuer ?? ""),
    `<span class="holding-bar" style="width:${Math.max(4, (holding.weight / top) * 120)}px"></span>`,
    weight(holding.weight),
    money(holding.value),
  ]);
  return table([{ label: "Ticker" }, { label: "Company" }, { label: "" }, { label: "Weight", num: true }, { label: "Value", num: true }], rows);
}

function optionsTable(options) {
  if (!options?.length) return "";
  const rows = options.map((option) => [
    `<strong>${escapeHtml(option.ticker ?? "—")}</strong>`, escapeHtml(option.issuer ?? ""),
    `<span class="badge ${String(option.put_call).toUpperCase() === "PUT" ? "oppose" : "approve"}">${escapeHtml(String(option.put_call).toUpperCase() === "PUT" ? "Put (bet it falls)" : "Call (bet it rises)")}</span>`,
    money(option.value),
  ]);
  return `<section class="section"><h2>Option bets</h2>
    <p class="lede">Puts and calls are bets on a stock's direction, reported at the value of the stock behind them. They are
      not counted in the portfolio weights.</p>
    <div class="card">${table([{ label: "Ticker" }, { label: "Company" }, { label: "Type" }, { label: "Value of stock behind it", num: true }], rows)}</div></section>`;
}

function analysisHtml(analysis) {
  if (!analysis) return "";
  const simulation = analysis.simulation ?? {};
  return `<div class="grid cols-4">
      ${metricCard({ label: "Expected return", value: percent(analysis.expected_return), medium: true, note: "Average of the stocks' past monthly returns, per year." })}
      ${metricCard({ label: "Volatility", value: percent(analysis.volatility), medium: true })}
      ${metricCard({ label: "Worst 12 months", value: percent(analysis.worst_12_month_return), medium: true, tone: "caution" })}
      ${metricCard({ label: "Effective holdings", value: Number(analysis.effective_number_of_holdings ?? 0).toFixed(1), medium: true, note: "How many equal-sized holdings this behaves like." })}
    </div>
    <div class="grid cols-2" style="margin-top:18px">
      <div class="card stack"><h3>Checked against the foundation's rules</h3>${verdictChips(analysis.verdicts)}</div>
      <div class="card stack"><h3>If the $100 million foundation held it for seven years</h3>
        <div class="kv"><span>Chance of meeting the objective</span><span>${percent(simulation.probability_objective, 1)}</span></div>
        <div class="kv"><span>Chance of dipping below $90 million</span><span>${percent(simulation.probability_below_90m, 1)}</span></div>
        <div class="kv"><span>Median ending value</span><span>${moneyShort(simulation.median_ending_value)}</span></div>
      </div>
    </div>
    ${analysis.hindsight_note ? `<div class="banner info" style="margin-top:18px"><span>i</span><span>${escapeHtml(analysis.hindsight_note)}</span></div>` : ""}`;
}

export async function renderLegend(root, key, navigate) {
  const who = PEOPLE[key] ?? PEOPLE.buffett;
  root.innerHTML = `<div class="page">
    <a class="no-print" href="#/legends">← All legends</a>
    <h1 style="margin-top:12px;font-size:44px">${escapeHtml(who.person)}</h1>
    <p class="muted" style="margin-top:8px">${escapeHtml(who.firm)} · ${escapeHtml(who.style)}</p>
    <div id="legend-body" style="margin-top:24px">${skeleton("Reading the 13F filing and screening the top holdings...", 320)}</div>
  </div>`;
  const body = root.querySelector("#legend-body");
  let detail;
  try {
    detail = await getLegend(`/api/legends/${key}?top_n=10`);
  } catch (error) {
    body.innerHTML = errorCard(error.message);
    return;
  }
  const holdings = detail.holdings ?? [];
  const summary = detail.summary ?? detail;
  body.innerHTML = `
    ${staleBanner(summary)}
    <div class="grid cols-3" style="margin-top:12px">
      ${metricCard({ label: "Holdings report for", value: dateLong(detail.report_period ?? summary.report_period), medium: true, note: `Filed ${dateLong(detail.filing_date ?? summary.filing_date)}.` })}
      ${metricCard({ label: "Stocks held", value: String(holdings.length), medium: true, note: `Top 5 are ${percent(summary.top_5_weight, 0)} of the portfolio.` })}
      ${metricCard({ label: "Total stock value", value: moneyShort(holdings.reduce((sum, holding) => sum + (holding.value ?? 0), 0)), medium: true })}
    </div>
    <div class="card stack" style="margin-top:18px">
      <h3>Build a plan from this portfolio</h3>
      <p class="muted">Loads the top 10 stocks into your personal plan, plus SGOV (cash) and IEF (government bonds), because a
        plan with only stocks cannot hold a safety reserve. Compass then finds the best mix under your rules, with each stock
        capped at 10%.</p>
      <div class="fund-tools"><button class="button" type="button" data-start>Use these stocks in my plan</button>
        <button class="button ghost" type="button" data-analyze>Analyze the top 10 as a $100,000 portfolio</button></div>
      <div data-start-message></div>
    </div>
    <section class="section"><h2>Holdings</h2><div class="card">${holdingsTable(holdings)}</div>
      ${detail.unmapped_cusips?.length ? `<p class="caption">${detail.unmapped_cusips.length} holding(s) could not be matched to a ticker and are left out of plans.</p>` : ""}</section>
    ${optionsTable(detail.options)}
    <section class="section"><h2>Would ${escapeHtml(who.person.split(" ")[1])}'s checks pass these stocks?</h2>
      <p class="lede">Buffett's and Burry's checks from my Lab 18 and 19 skills, run on each company's own annual reports,
        using only reports filed by the decision date.</p>
      ${screensHtml(detail.screens ?? [])}</section>
    <section class="section"><h2>The top 10 as a portfolio</h2>
      <p class="lede">The ten largest stock holdings at their filing weights, tested like any other portfolio.</p>
      <div id="legend-analysis">${skeleton("Downloading prices from Yahoo Finance and running 10,000 simulations...", 160)}</div></section>`;

  const top10 = holdings.filter((holding) => holding.ticker).slice(0, 10);
  const top10Total = top10.reduce((sum, holding) => sum + (holding.weight ?? 0), 0) || 1;
  body.querySelector("[data-analyze]").addEventListener("click", () => {
    openInAnalyze(Object.fromEntries(top10.map((holding) => [
      holding.ticker, Math.round((holding.weight / top10Total) * 100000)])), navigate);
  });
  setAssistantContext(`Legends: ${who.person}`, [
    `${who.person} (${who.firm}) 13F report for ${detail.report_period ?? summary.report_period}, filed ${detail.filing_date ?? summary.filing_date}`,
    `Stocks held: ${holdings.length}; top 5 are ${percent(summary.top_5_weight, 0)} of the portfolio`,
    ...top10.map((holding) => `${holding.ticker} (${holding.issuer ?? ""}): ${weight(holding.weight)} of the portfolio`),
  ], [
    `What does ${who.person.split(" ")[1]} own?`,
    "What is a 13F?",
    "What is diversification?",
  ]);

  body.querySelector("[data-start]").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const message = body.querySelector("[data-start-message]");
    button.disabled = true;
    try {
      const response = await getLegend(`/api/legends/${key}/universe?top_n=10`);
      const stocks = (response.universe ?? response.funds ?? response.tickers ?? []).map((fund) => (
        typeof fund === "string" ? { ticker: fund, role: "individual stock", reserve_eligible: false } : fund));
      const safety = DEFAULT_UNIVERSE.filter((fund) => ["SGOV", "IEF"].includes(fund.ticker));
      const universe = [...safety, ...stocks.filter((fund) => !["SGOV", "IEF"].includes(fund.ticker))].slice(0, 15)
        .map((fund) => ({ ticker: fund.ticker, name: fund.name ?? fund.issuer ?? fund.ticker, role: fund.role ?? "individual stock", reserve_eligible: Boolean(fund.reserve_eligible) }));
      registerFunds(universe);
      saveInputs({ ...loadInputs(), universe });
      navigate("#/personal/plan");
    } catch (error) {
      message.innerHTML = `<div class="banner bad" style="margin-top:8px"><span>✕</span><span>${escapeHtml(error.message)}</span></div>`;
      button.disabled = false;
    }
  });

  try {
    const analysis = await getLegend(`/api/legends/${key}/analysis?top_n=10`);
    const target = body.querySelector("#legend-analysis");
    if (target) target.innerHTML = analysisHtml(analysis);
  } catch (error) {
    const target = body.querySelector("#legend-analysis");
    if (target) target.innerHTML = errorCard(error.message);
  }
}

export { chip };
