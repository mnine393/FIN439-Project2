// Analyze: type in any portfolio (tickers and dollars) and see its risk, history, crisis replays,
// a forecast range from two methods, and a test of how accurate past forecasts were.
import { setAssistantContext, explainButton } from "./assistant.js";
import {
  bars, calibrationChart, donut, fanCompare, growthAndDrawdown, heatmap, scenarioBars,
} from "./charts.js";
import { escapeHtml, fundColor, money, moneyShort, monthName, parseMoney, percent, term, weight } from "./format.js";
import { errorCard, metricCard, skeleton, table } from "./ui.js";

const STORE_KEY = "compass.analyze.v1";

export const PRESETS = {
  "Classic 60/40": { VT: 60000, IEF: 40000 },
  "Three-fund": { VTI: 50000, VXUS: 30000, BND: 20000 },
  "All-weather style": { VTI: 30000, TLT: 40000, IEI: 15000, GLD: 7500, DBC: 7500 },
  "Compass default": { SGOV: 3000, IEF: 25000, USIG: 12000, VT: 60000 },
  "Big tech tilt": { VOO: 50000, QQQ: 20000, AAPL: 10000, MSFT: 10000, NVDA: 10000 },
};

const COMPARE_WITH = {
  "Classic 60/40": { VT: 0.6, IEF: 0.4 },
  "All stocks (VT)": { VT: 1 },
  "Three-fund": { VTI: 0.5, VXUS: 0.3, BND: 0.2 },
};

const HORIZONS = [1, 3, 5, 10, 20, 30];

function loadState() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(STORE_KEY) ?? "null");
    if (saved?.holdings && Object.keys(saved.holdings).length) return saved;
  } catch (error) { /* private mode or blocked storage: start fresh */ }
  return { holdings: { ...PRESETS["Classic 60/40"] }, horizon: 10, monthly: 0 };
}

function saveState(state) {
  try {
    window.localStorage.setItem(STORE_KEY, JSON.stringify(state));
  } catch (error) { /* not saved; the page still works */ }
}

/** Other pages (and the AI) can hand a portfolio to this page. */
export function openInAnalyze(holdings, navigate) {
  const state = loadState();
  state.holdings = Object.fromEntries(Object.entries(holdings).map(([ticker, value]) => [ticker.toUpperCase(), Number(value)]));
  saveState(state);
  navigate("#/analyze/run");
}

async function post(path, body) {
  let response;
  try {
    response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  } catch (error) {
    throw new Error("The Compass service is not reachable. Start it with: python run.py");
  }
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail;
    throw new Error(Array.isArray(detail) ? detail.map((item) => item.msg).join("; ") : detail ?? `Request failed (${response.status}).`);
  }
  return payload;
}

// ---------- the input form ----------

function holdingsRows(holdings) {
  return Object.entries(holdings).map(([ticker, value], index) => `
    <div class="holding-row" data-index="${index}">
      <span class="dot" style="background:${fundColor(ticker)}"></span>
      <input class="input ticker-input" value="${escapeHtml(ticker)}" aria-label="Ticker" maxlength="10" spellcheck="false">
      <input class="input money-input" value="${money(value)}" aria-label="Dollars in ${escapeHtml(ticker)}" inputmode="decimal">
      <button class="icon-button remove-holding" type="button" aria-label="Remove ${escapeHtml(ticker)}">✕</button>
    </div>`).join("");
}

function readHoldings(form) {
  const holdings = {};
  form.querySelectorAll(".holding-row").forEach((row) => {
    const ticker = row.querySelector(".ticker-input").value.trim().toUpperCase();
    const value = parseMoney(row.querySelector(".money-input").value);
    if (ticker && value > 0) holdings[ticker] = (holdings[ticker] ?? 0) + value;
  });
  return holdings;
}

function formHtml(state) {
  const total = Object.values(state.holdings).reduce((sum, value) => sum + value, 0);
  return `
  <section class="analyze-hero">
    <div>
      <span class="eyebrow">Portfolio analyzer</span>
      <h1>See how any portfolio behaves, and where it could go.</h1>
      <p class="lede">Type in what you own. Compass replays real crises, shows where the risk really comes from,
        and forecasts a range of outcomes with a method that is tested against its own past forecasts.</p>
      <div class="hero-points">
        <span>✓ Any ticker on Yahoo Finance</span><span>✓ Point-in-time data</span><span>✓ Forecasts checked against history</span>
      </div>
    </div>
    <form class="card stack" id="analyze-form" autocomplete="off">
      <div class="card-head"><h3>Your portfolio</h3><span class="muted num" id="holdings-total">${money(total)}</span></div>
      <div class="preset-row">${Object.keys(PRESETS).map((name) => (
        `<button class="pill" type="button" data-preset="${escapeHtml(name)}">${escapeHtml(name)}</button>`)).join("")}
        <button class="pill accent" type="button" id="open-quiz">Take the risk quiz</button></div>
      <div class="holding-list" id="holding-list">${holdingsRows(state.holdings)}</div>
      <button class="button ghost small" type="button" id="add-holding">+ Add a holding</button>
      <div class="form-grid">
        <label class="field">Forecast horizon
          <select class="input" id="horizon">${HORIZONS.map((years) => (
            `<option value="${years}" ${years === state.horizon ? "selected" : ""}>${years} ${years === 1 ? "year" : "years"}</option>`)).join("")}</select>
        </label>
        <label class="field">Monthly contribution
          <input class="input" id="monthly" value="${money(state.monthly)}" inputmode="decimal">
          <span class="hint">Use a minus sign for withdrawals.</span>
        </label>
      </div>
      <button class="button block" type="submit">Analyze portfolio</button>
    </form>
  </section>`;
}

// ---------- the risk quiz ----------

async function openQuiz(onPick) {
  const dialog = document.createElement("dialog");
  dialog.className = "quiz";
  dialog.innerHTML = skeleton("Loading the questions…", 200);
  document.body.appendChild(dialog);
  dialog.showModal();
  dialog.addEventListener("close", () => dialog.remove());
  try {
    const response = await fetch("/api/risk-profile/questions");
    const { questions } = await response.json();
    dialog.innerHTML = `<form method="dialog" class="stack" id="quiz-form">
      <div class="card-head"><h2>Risk quiz</h2><button class="icon-button" value="cancel" aria-label="Close">✕</button></div>
      <p class="muted">Five questions. Your answers set a 1-to-10 risk score and a starting stock share.</p>
      ${questions.map((question) => `<fieldset class="quiz-question"><legend>${escapeHtml(question.question)}</legend>
        <div class="quiz-options">${question.labels.map((label, index) => `<label><input type="radio" name="${question.key}" value="${index + 1}" ${index === 2 ? "checked" : ""}>
        <span>${escapeHtml(label)}</span></label>`).join("")}</div></fieldset>`).join("")}
      <div id="quiz-result"></div>
      <button class="button block" type="button" id="quiz-score">See my score</button>
    </form>`;
    dialog.querySelector("#quiz-score").addEventListener("click", async () => {
      const answers = Object.fromEntries(questions.map((question) => [
        question.key, Number(dialog.querySelector(`input[name="${question.key}"]:checked`).value)]));
      const result = await post("/api/risk-profile", { answers });
      const stocks = result.suggested_stock_share;
      const bonds = Math.max(0, 1 - stocks - 0.05);
      const mix = { VT: Math.round(stocks * 100000), IEF: Math.round(bonds * 100000), SGOV: Math.round(0.05 * 100000) };
      dialog.querySelector("#quiz-result").innerHTML = `<div class="banner info"><span>●</span><span>Risk score ${result.score} of 10.
        Suggested starting point: about ${weight(stocks)} stocks.
        <span class="detail">Starting mix: VT ${weight(stocks)}, IEF ${weight(bonds)}, SGOV 5%, on $100,000. You can change it.</span></span></div>`;
      const button = dialog.querySelector("#quiz-score");
      button.textContent = "Analyze this mix";
      button.onclick = () => { dialog.close(); onPick(mix); };
    });
  } catch (error) {
    dialog.innerHTML = errorCard(error.message);
  }
}

// ---------- results ----------

function horizonLabel(months) {
  const years = Number(months) / 12;
  return `${years} ${years === 1 ? "year" : "years"}`;
}

function riskGauge(score) {
  const cells = Array.from({ length: 10 }, (_, index) => `<i class="${index < score ? "on" : ""}" style="--i:${index}"></i>`).join("");
  return `<div class="gauge" role="img" aria-label="Risk score ${score} of 10">${cells}</div>`;
}

function flagsHtml(flags) {
  if (!flags?.length) return `<div class="banner good"><span>✓</span><span>No warning flags for this portfolio.</span></div>`;
  return flags.map((flag) => `<div class="banner caution"><span>!</span><span>${escapeHtml(flag)}</span></div>`).join("");
}

function percentileTable(improved, simple) {
  const keys = Object.keys(improved.percentiles);
  const rows = keys.map((key) => {
    const better = improved.percentiles[key];
    const plain = simple.percentiles[key] ?? {};
    return [horizonLabel(key), moneyShort(better.p10), `<b>${moneyShort(better.p50)}</b>`, moneyShort(better.p90),
      `<span class="muted">${moneyShort(plain.p50)}</span>`];
  });
  return table([{ label: "After" }, { label: "Poor (10th)", num: true }, { label: "Median", num: true },
    { label: "Strong (90th)", num: true }, { label: "Simple method median", num: true }], rows);
}

function assumptionsTable(assumptions) {
  const rows = Object.entries(assumptions).map(([ticker, row]) => [
    `<span class="dot" style="background:${fundColor(ticker)}"></span> <b>${escapeHtml(ticker)}</b>`,
    percent(row.history_mean), percent(row.forward_estimate), `<b>${percent(row.blended)}</b>`,
    `<span class="muted" style="font-size:12.5px">${escapeHtml(row.basis)}</span>`]);
  return table([{ label: "Holding" }, { label: "History", num: true }, { label: "Forward-looking", num: true },
    { label: "Used (blend)", num: true }, { label: "Basis" }], rows);
}

function statsList(history) {
  const items = [
    ["Return per year (history)", percent(history.annual_return)],
    [term("Volatility", "Volatility per year"), percent(history.volatility)],
    [term("Sharpe ratio"), history.sharpe_ratio?.toFixed(2) ?? "not known"],
    [term("Sortino ratio"), history.sortino_ratio?.toFixed(2) ?? "not known"],
    [term("Largest drop"), `${percent(history.maximum_drawdown)} (${monthName(history.maximum_drawdown_start)} to ${monthName(history.maximum_drawdown_end)})`],
    ["Best 12 months", percent(history.best_12_months)],
    ["Worst 12 months", percent(history.worst_12_months)],
    [term("Beta", "Beta to global stocks"), history.beta?.toFixed(2) ?? "not known"],
  ];
  return items.map(([key, value]) => `<div class="kv"><span>${key}</span><span>${escapeHtml(value)}</span></div>`).join("");
}

function feesHtml(fees, total) {
  const rows = Object.entries(fees.by_holding).map(([ticker, fee]) => [
    escapeHtml(ticker), typeof fee === "number" ? percent(fee, 2) : "not known"]);
  const headline = fees.weighted_portfolio_fee == null
    ? "Some fees are not known"
    : `${percent(fees.weighted_portfolio_fee, 2)} a year · ${money(fees.dollars_per_year)} on ${money(total)}`;
  return `<p class="big-line">${escapeHtml(headline)}</p><p class="muted">Each fund's ${term("Expense ratio", "expense ratio")}:</p>${table([{ label: "Holding" }, { label: "Expense ratio", num: true }], rows)}
    <p class="caption">${escapeHtml(fees.source)}. Individual stocks have no fund fee.</p>`;
}

function scenarioCards(scenarios) {
  return scenarios.map((row) => {
    const proxies = Object.entries(row.sources ?? {}).filter(([, source]) => source === "proxy").map(([ticker]) => ticker);
    return `<div class="card scenario ${row.portfolio_return < 0 ? "loss" : "gain"}">
      <div class="label">${escapeHtml(row.name)}</div>
      <div class="value num">${percent(row.portfolio_return, 1)}</div>
      <div class="note">${escapeHtml(row.period)} · ${row.dollars_lost > 0 ? `${moneyShort(row.dollars_lost)} lost` : `${moneyShort(-row.dollars_lost)} gained`}</div>
      ${row.worst_month != null ? `<div class="note">Worst month ${percent(row.worst_month, 1)}</div>` : ""}
      ${proxies.length ? `<div class="note muted">Estimated for ${escapeHtml(proxies.join(", "))} (no data then)</div>` : ""}
    </div>`;
  }).join("");
}

function contextLines(result, state) {
  const improved = result.forecast.improved;
  const last = Object.keys(improved.percentiles).at(-1);
  const band = improved.percentiles[last];
  return [
    `Portfolio: ${Object.entries(state.holdings).map(([ticker, value]) => `${ticker} ${money(value)}`).join(", ")}`,
    `Total value: ${money(result.total_value)}`,
    `Risk score: ${result.risk_score.score} of 10`,
    `History: return ${percent(result.history.annual_return)} a year, volatility ${percent(result.history.volatility)}, largest drop ${percent(result.history.maximum_drawdown)}`,
    `Improved forecast after ${horizonLabel(last)}: 10th percentile ${moneyShort(band.p10)}, median ${moneyShort(band.p50)}, 90th percentile ${moneyShort(band.p90)}`,
    `Expected return used by the improved forecast: ${percent(improved.expected_annual_return)}`,
    `Chance of ending with less than was put in: ${percent(improved.probability_losing_money, 1)}`,
    ...result.crisis_scenarios.map((row) => `${row.name}: ${percent(row.portfolio_return, 1)}`),
    ...result.flags.map((flag) => `Flag: ${flag}`),
  ];
}

function resultsHtml(result, state) {
  const improved = result.forecast.improved;
  const simple = result.forecast.simple;
  const last = Object.keys(improved.percentiles).at(-1);
  const band = improved.percentiles[last];
  const score = result.risk_score.score;
  const tone = score >= 8 ? "bad" : score >= 5 ? "caution" : "good";
  return `
  <div class="grid cols-4 section" id="headline">
    ${metricCard({ label: "Portfolio value", value: moneyShort(result.total_value), medium: true,
      note: `${result.concentration.number_of_holdings} holdings · acts like ${result.concentration.effective_number_of_holdings.toFixed(1)} equal ones` })}
    ${metricCard({ label: "Risk score", value: `${score} / 10`, tone, medium: true, extra: riskGauge(score), note: escapeHtml(result.risk_score.meaning) })}
    ${metricCard({ label: "Expected return", value: percent(improved.expected_annual_return), medium: true,
      note: `a year, improved method (history alone: ${percent(result.history.annual_return)})` })}
    ${metricCard({ label: `Median after ${horizonLabel(last)}`, value: moneyShort(band.p50), medium: true, tone: "good",
      note: `80% range ${moneyShort(band.p10)} to ${moneyShort(band.p90)}` })}
  </div>
  <div class="stack section" style="margin-top:18px">${flagsHtml(result.flags)}</div>

  <section class="section" id="forecast">
    <div class="card-head"><h2>Where it could go</h2>${explainButton("Explain the forecast on the Analyze page: what the range means and why the improved and simple methods differ.")}</div>
    <p class="lede">10,000 simulated futures. The improved method draws whole 12-month stretches of real history (so crashes
      stay intact), starts from today's bond yields instead of assuming the last 18 years repeat, and allows for not
      knowing the true average return. The grey dashed lines are the simple method for comparison.</p>
    <div class="card"><div class="chart tall" id="fan-chart"></div>
      <div class="grid cols-3" style="margin-top:12px">
        <div class="mini"><span>Chance of ending below the money put in</span><b>${percent(improved.probability_losing_money, 1)}</b></div>
        <div class="mini"><span>Chance of a 20% drop along the way</span><b>${percent(improved.probability_20_percent_drawdown, 1)}</b></div>
        <div class="mini"><span>${term("Volatility")} used (shrunk estimate)</span><b>${percent(improved.annual_volatility)}</b></div>
      </div>
    </div>
    <div class="grid cols-2" style="margin-top:18px">
      <div class="card"><h3>Range of outcomes</h3><p class="muted">Read across: a poor, a middle (${term("Median", "median")}) and a strong future. ${term("Percentile", "What is a percentile?")}</p>${percentileTable(improved, simple)}</div>
      <div class="card"><h3>Expected returns used</h3>${assumptionsTable(improved.assumptions)}
        <p class="caption">Forward-looking: bills and bonds earn about their starting yield; stocks earn the bill yield plus
          beta times a 4.5% equity risk premium. The forecast uses a 50/50 blend with history.</p></div>
    </div>
  </section>

  <section class="section" id="calibration">
    <div class="card-head"><h2>How good are these forecasts?</h2>${explainButton("Explain the forecast accuracy test: what calibration means and whether the improved method is better than the simple one.")}</div>
    <p class="lede">At every month in the past, Compass makes the forecast it would have made then, using only data known
      then, and checks what really happened. A well-${term("Calibration", "calibrated")} forecast's 10th-to-90th range catches about 80% of outcomes.</p>
    <div class="card" id="calibration-card">
      <button class="button" type="button" id="run-calibration">Run the accuracy test</button>
      <span class="muted" style="margin-left:10px">Takes up to a minute the first time; saved after that.</span>
    </div>
  </section>

  <section class="section" id="risk">
    <div class="card-head"><h2>Where the risk comes from</h2>${explainButton("Explain risk contribution versus weight for this portfolio on the Analyze page.")}</div>
    <p class="lede">A holding's share of the risk is often very different from its share of the money.</p>
    <div class="grid cols-2">
      <div class="card"><h3>What you own</h3><div class="chart" id="donut-chart"></div></div>
      <div class="card"><h3>Share of money versus ${term("Share of risk", "share of risk")}</h3><div class="chart" id="risk-chart"></div>
        <p class="caption">${term("Diversification ratio")} ${result.diversification_ratio.toFixed(2)} (above 1 means the holdings offset each other).</p></div>
    </div>
  </section>

  <section class="section" id="crises">
    <div class="card-head"><h2>Crisis replays</h2>${explainButton("Explain the crisis replays for this portfolio: which holdings hurt and which helped.")}</div>
    <p class="lede">What this exact portfolio would have done in real market crises, plus one hypothetical high-inflation year.</p>
    <div class="grid cols-4">${scenarioCards(result.crisis_scenarios)}</div>
    <div class="card" style="margin-top:18px"><div class="chart" id="scenario-chart"></div></div>
  </section>

  <section class="section" id="history">
    <h2>History</h2>
    <p class="lede">Monthly total returns from Yahoo Finance over the months all holdings existed.</p>
    <div class="grid cols-2">
      <div class="card"><div class="chart tall" id="growth-chart"></div></div>
      <div class="card"><h3>Statistics</h3>${statsList(result.history)}</div>
    </div>
  </section>

  <section class="section" id="correlation">
    <h2>How the holdings move together (${term("Correlation", "correlation")})</h2>
    <p class="lede">1 means they always move together; near 0 means unrelated; below 0 means they tend to offset.
      Estimated with shrinkage (intensity ${percent(result.correlation.shrinkage_intensity, 0)}) so noise counts less.</p>
    <div class="grid cols-2">
      <div class="card"><div class="chart" id="heatmap-chart"></div></div>
      <div class="card"><h3>Fees</h3>${feesHtml(result.fees, result.total_value)}</div>
    </div>
  </section>

  <section class="section" id="compare">
    <div class="card-head"><h2>Compare</h2>
      <select class="input" id="compare-with" style="width:auto">${Object.keys(COMPARE_WITH).map((name) => `<option>${escapeHtml(name)}</option>`).join("")}</select></div>
    <div class="card" id="compare-card">${skeleton("Comparing…", 120)}</div>
  </section>`;
}

/** The service reports risk shares in percent (adding to 100); charts use fractions like the weights. */
function riskShares(contributions) {
  const total = Object.values(contributions).reduce((sum, value) => sum + value, 0);
  const scale = total > 1.5 ? 100 : 1;
  return Object.fromEntries(Object.entries(contributions).map(([ticker, value]) => [ticker, value / scale]));
}

/** True when two portfolios hold the same tickers in the same proportions. */
function sameMix(holdings, shares) {
  const total = Object.values(holdings).reduce((sum, value) => sum + value, 0);
  const tickers = new Set([...Object.keys(holdings), ...Object.keys(shares)]);
  return [...tickers].every((ticker) => Math.abs((holdings[ticker] ?? 0) / total - (shares[ticker] ?? 0)) < 0.005);
}

function drawResults(result, state) {
  const improved = result.forecast.improved;
  const months = Number(Object.keys(improved.percentiles).at(-1));
  fanCompare(document.querySelector("#fan-chart"), improved.fan, result.forecast.simple.fan,
    result.total_value + state.monthly * months);
  donut(document.querySelector("#donut-chart"), result.weights, Object.fromEntries(
    Object.entries(result.weights).map(([ticker, share]) => [ticker, share * result.total_value])));
  const labels = Object.keys(result.weights).map((ticker) => ({ label: ticker }));
  bars(document.querySelector("#risk-chart"), labels, {
    title: "Share (%)",
    group: [
      { name: "Share of money", values: result.weights, color: "#9AA7B4" },
      { name: "Share of risk", values: riskShares(result.risk_contribution), color: "#D64545" },
    ],
  });
  scenarioBars(document.querySelector("#scenario-chart"), result.crisis_scenarios);
  growthAndDrawdown(document.querySelector("#growth-chart"), result.growth_of_10000, result.drawdown_series);
  heatmap(document.querySelector("#heatmap-chart"), result.correlation.tickers, result.correlation.matrix);
}

async function runCalibration(state) {
  const card = document.querySelector("#calibration-card");
  card.innerHTML = skeleton("Making hundreds of past forecasts and checking each one…", 200);
  try {
    const result = await post("/api/calibration", { holdings: state.holdings });
    const methods = result.methods;
    const horizons = Object.keys(methods.improved ?? methods.simple);
    const name = { simple: "Simple method", improved: "Improved method" };
    const rows = [];
    for (const method of Object.keys(methods)) {
      for (const horizon of horizons) {
        const row = methods[method][horizon];
        const gap = Math.abs(row.inside_10_90 - 0.8);
        rows.push([name[method] ?? method, horizonLabel(horizon), row.number_of_forecasts,
          `<b class="${gap <= 0.07 ? "good-text" : gap <= 0.15 ? "caution-text" : "bad-text"}">${percent(row.inside_10_90, 0)}</b>`,
          percent(row.below_10, 0), percent(row.above_90, 0), row.pinball_loss.toFixed(4)]);
      }
    }
    card.innerHTML = `${table([{ label: "Method" }, { label: "Horizon" }, { label: "Forecasts", num: true },
      { label: "Inside the 80% range (target 80%)", num: true }, { label: "Below it", num: true },
      { label: "Above it", num: true }, { label: "Average error score (lower is better)", num: true }], rows)}
      <div class="chart-tabs" role="tablist">${Object.keys(methods).flatMap((method) => horizons.map((horizon) => (
        `<button class="pill" type="button" data-cal="${method}|${horizon}">${name[method] ?? method}, ${horizonLabel(horizon)}</button>`))).join("")}</div>
      <div class="chart tall" id="calibration-chart"></div>
      <p class="caption">Each shaded slice is the range a forecast gave on that date; dots are what actually happened
        over the next period. Red dots fell outside the range.</p>`;
    const show = (key) => {
      const [method, horizon] = key.split("|");
      card.querySelectorAll("[data-cal]").forEach((button) => button.classList.toggle("active", button.dataset.cal === key));
      calibrationChart(card.querySelector("#calibration-chart"), methods[method][horizon].outcomes, horizonLabel(horizon));
    };
    card.querySelectorAll("[data-cal]").forEach((button) => button.addEventListener("click", () => show(button.dataset.cal)));
    show(`${methods.improved ? "improved" : "simple"}|${horizons[0]}`);
  } catch (error) {
    card.innerHTML = errorCard(error.message);
  }
}

async function runCompare(state) {
  const card = document.querySelector("#compare-card");
  const choice = document.querySelector("#compare-with").value;
  const total = Object.values(state.holdings).reduce((sum, value) => sum + value, 0);
  const other = Object.fromEntries(Object.entries(COMPARE_WITH[choice]).map(([ticker, share]) => [ticker, share * total]));
  card.innerHTML = skeleton("Comparing…", 120);
  try {
    const result = await post("/api/compare", { a: state.holdings, b: other, horizon_years: state.horizon });
    const a = result.details.a;
    const b = result.details.b;
    const lastA = Object.keys(a.forecast.improved.percentiles).at(-1);
    const lastB = Object.keys(b.forecast.improved.percentiles).at(-1);
    const line = (label, left, right) => [escapeHtml(label), left, right];
    card.innerHTML = table([{ label: "" }, { label: "Your portfolio", num: true }, { label: choice, num: true }], [
      line("Risk score", `${a.risk_score.score} / 10`, `${b.risk_score.score} / 10`),
      line("Expected return (improved)", percent(a.forecast.improved.expected_annual_return), percent(b.forecast.improved.expected_annual_return)),
      line("Return per year (history)", percent(a.history.annual_return), percent(b.history.annual_return)),
      line("Volatility", percent(a.history.volatility), percent(b.history.volatility)),
      line("Largest drop", percent(a.history.maximum_drawdown), percent(b.history.maximum_drawdown)),
      line("Sharpe ratio", a.history.sharpe_ratio?.toFixed(2) ?? "not known", b.history.sharpe_ratio?.toFixed(2) ?? "not known"),
      line(`Median after ${horizonLabel(lastA)}`, moneyShort(a.forecast.improved.percentiles[lastA].p50), moneyShort(b.forecast.improved.percentiles[lastB].p50)),
      line("Poor case (10th percentile)", moneyShort(a.forecast.improved.percentiles[lastA].p10), moneyShort(b.forecast.improved.percentiles[lastB].p10)),
      line("2008 crisis replay", percent(a.crisis_scenarios[0].portfolio_return, 1), percent(b.crisis_scenarios[0].portfolio_return, 1)),
      line("Fee per year", a.fees.weighted_portfolio_fee == null ? "not known" : percent(a.fees.weighted_portfolio_fee),
        b.fees.weighted_portfolio_fee == null ? "not known" : percent(b.fees.weighted_portfolio_fee)),
    ]);
    card.insertAdjacentHTML("beforeend", `<p class="caption">Both portfolios are measured over the same months (the
      months every holding in either one has data), so figures can differ slightly from the sections above.</p>`);
  } catch (error) {
    card.innerHTML = errorCard(error.message);
  }
}

export async function renderAnalyze(root, navigate, { autorun = false } = {}) {
  const state = loadState();
  root.innerHTML = `<div class="page">${formHtml(state)}<div id="analyze-results"></div></div>`;
  const form = root.querySelector("#analyze-form");
  const list = form.querySelector("#holding-list");
  setAssistantContext("Analyze (portfolio analyzer)", [
    `Portfolio being entered: ${Object.entries(state.holdings).map(([ticker, value]) => `${ticker} ${money(value)}`).join(", ")}`,
  ], [
    "Analyze 50000 VTI, 30000 VXUS, 20000 BND",
    "Make this safer",
    "Is this portfolio diversified enough?",
  ], { holdings: state.holdings });

  const refreshTotal = () => {
    const total = Object.values(readHoldings(form)).reduce((sum, value) => sum + value, 0);
    form.querySelector("#holdings-total").textContent = money(total);
  };
  const setHoldings = (holdings) => {
    list.innerHTML = holdingsRows(holdings);
    refreshTotal();
  };
  list.addEventListener("input", refreshTotal);
  list.addEventListener("change", (event) => {
    if (event.target.classList.contains("money-input")) event.target.value = money(parseMoney(event.target.value));
    if (event.target.classList.contains("ticker-input")) {
      event.target.value = event.target.value.trim().toUpperCase();
      event.target.parentElement.querySelector(".dot").style.background = fundColor(event.target.value);
    }
  });
  list.addEventListener("click", (event) => {
    if (event.target.closest(".remove-holding")) {
      event.target.closest(".holding-row").remove();
      refreshTotal();
    }
  });
  form.querySelector("#add-holding").addEventListener("click", () => {
    const holdings = readHoldings(form);
    list.insertAdjacentHTML("beforeend", holdingsRows({ "": 10000 }).replace('data-index="0"', `data-index="${Object.keys(holdings).length}"`));
    list.querySelector(".holding-row:last-child .ticker-input").focus();
    refreshTotal();
  });
  form.querySelectorAll("[data-preset]").forEach((button) => button.addEventListener("click", () => setHoldings(PRESETS[button.dataset.preset])));
  form.querySelector("#open-quiz").addEventListener("click", () => openQuiz((mix) => {
    setHoldings(mix);
    form.requestSubmit();
  }));

  const results = root.querySelector("#analyze-results");
  const run = async () => {
    state.holdings = readHoldings(form);
    state.horizon = Number(form.querySelector("#horizon").value);
    const monthlyText = form.querySelector("#monthly").value;
    state.monthly = parseMoney(monthlyText) * (monthlyText.trim().startsWith("-") ? -1 : 1);
    if (Object.keys(state.holdings).length < 1) {
      results.innerHTML = errorCard("Add at least one holding with a dollar amount.");
      return;
    }
    saveState(state);
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    button.innerHTML = `<span class="spinner"></span>Analyzing…`;
    results.innerHTML = `<div class="section">${skeleton("Downloading prices, replaying crises and simulating 10,000 futures…", 260)}</div>`;
    try {
      const result = await post("/api/analyze", { holdings: state.holdings, horizon_years: state.horizon, monthly_flow: state.monthly });
      results.innerHTML = resultsHtml(result, state);
      drawResults(result, state);
      setAssistantContext("Analyze (portfolio analyzer) results", contextLines(result, state), [
        "Make this safer",
        "Which holding adds the most risk?",
        "How did this portfolio do in 2008?",
      ], { holdings: state.holdings });
      results.querySelector("#run-calibration").addEventListener("click", () => runCalibration(state));
      const compareSelect = results.querySelector("#compare-with");
      compareSelect.value = Object.keys(COMPARE_WITH).find((name) => !sameMix(state.holdings, COMPARE_WITH[name]));
      compareSelect.addEventListener("change", () => runCompare(state));
      runCompare(state);
      results.querySelector("#headline").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      results.innerHTML = `<div class="section">${errorCard(error.message)}</div>`;
    } finally {
      button.disabled = false;
      button.textContent = "Analyze portfolio";
    }
  };
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    run();
  });
  if (autorun) run();
}
