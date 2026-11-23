// Institution mode: the $100 million Meridian Foundation.
import { getInstitution } from "./api.js";
import * as charts from "./charts.js";
import { attachLiveReview, committeeHtml } from "./committee.js";
import {
  FUNDS, PORTFOLIO_COLORS, count, dateLong, escapeHtml, mixText, money, moneyShort, monthName, percent, points, weight,
} from "./format.js";
import {
  chip, errorCard, fundLegend, markdown, metricCard, portfolioCard, skeleton, stopBanner, stressTables, table,
  verdictChips, weightBar,
} from "./ui.js";
import { registerFunds } from "./format.js";
import { DEFAULT_UNIVERSE, isDefaultUniverse, renderUniverseEditor, universeQuery } from "./universe.js";
import { setAssistantContext } from "./assistant.js";

export const SECTIONS = [
  ["summary", "Committee summary"], ["mandate", "Mandate and compliance"], ["signal", "Inflation signal"],
  ["frontier", "Efficient frontier"], ["lasting", "Will the money last?"], ["worked", "Would it have worked?"],
  ["stress", "Stress lab"], ["locked", "Locked prediction"], ["committee", "Committee review"],
];

// Settings chosen in the stress lab; empty means the mandate's own defaults.
let settings = {};
// The holdings chosen in the stress lab; the four core funds unless the person changes them.
const institutionUniverse = { universe: DEFAULT_UNIVERSE.map((fund) => ({ ...fund })), custom: false };

function universeSettings() {
  if (!institutionUniverse.custom) return {};
  const query = universeQuery(institutionUniverse.universe);
  if (institutionUniverse.universe.some((fund) => fund.role === "individual stock")) {
    query.max_single_stock_weight = 0.10;
    query.max_individual_stocks_total = 0.40;
    if (institutionUniverse.universe.length >= 8) query.min_holdings = 5;
  }
  return query;
}

const planOf = (data) => data.portfolios.find((portfolio) => portfolio.name === "Constrained portfolio" && portfolio.weights) ?? null;
const named = (data, name) => data.portfolios.find((portfolio) => portfolio.name === name);
const dot = (name) => `<span class="dot" style="background:${PORTFOLIO_COLORS[name] ?? "#7A8797"}"></span>`;
const label = (name) => (name === "Constrained portfolio" ? "Constrained portfolio (the optimizer)" : name);

/* ------------------------------------------------------------------ sections */

function recommendationHtml(recommendation) {
  if (!recommendation?.decided) {
    return `<div class="card"><p class="group-title">Recommendation</p>
      <p style="font-size:20px;font-weight:750">Not yet decided</p>
      <p class="muted" style="margin-top:6px">The analyst's recommendation, allocation range and triggers will appear here.</p></div>`;
  }
  const triggers = (recommendation.triggers ?? []).map((trigger) => `<li>${escapeHtml(trigger)}</li>`).join("");
  return `<div class="card stack">
    <p class="group-title">Recommendation</p>
    <div style="font-size:30px;font-weight:800;line-height:1.2">${escapeHtml(recommendation.action)}</div>
    <div class="kv"><span>Allocation range</span><span>${escapeHtml(recommendation.allocation_range)}</span></div>
    <div class="kv"><span>Conditions</span><span>${escapeHtml(recommendation.conditions)}</span></div>
    <div><p class="group-title" style="margin-top:8px">Triggers to monitor</p><ul style="margin:6px 0 0;padding-left:20px">${triggers}</ul></div>
    <div class="banner info"><span>→</span><span>Committee ask: ${escapeHtml(recommendation.committee_ask)}</span></div>
  </div>`;
}

function summary(data) {
  const plan = planOf(data);
  const benchmark = named(data, "60/40 benchmark");
  const signal = data.cpi_signal;
  const objective = signal.inflation + data.mandate.objective_spread;
  const backtest = Object.fromEntries(data.backtest.table.map((row) => [row.portfolio, row]));
  const meeting = data.frontier.filter((mix) => mix.meets_mandate).length;
  const chance = plan?.simulation?.probability_objective;
  return `<h1 style="font-size:40px">${escapeHtml(data.mandate.name)}</h1>
    <p class="muted" style="margin-top:8px">A ${moneyShort(data.mandate.portfolio_size_dollars)} reserve that pays out
      ${money(data.mandate.cash_flow_amount)} every quarter. Decision date ${dateLong(signal.decision_date)}.</p>
    <div class="grid cols-3" style="margin-top:24px">
      ${metricCard({ label: "Inflation as known", value: percent(signal.inflation), note: `Consumer Price Index for ${monthName(signal.month)}, first published ${dateLong(signal.first_publication_date)}.` })}
      ${metricCard({ label: "Return objective", value: percent(objective), note: `Inflation as known plus ${percent(data.mandate.objective_spread, 0)}, over ${data.mandate.horizon_years} years.` })}
      ${metricCard({ label: "Chance the optimizer meets it", value: plan ? percent(chance, 0) : "No mix", tone: plan && chance >= 0.5 ? "caution" : "bad", note: plan ? `60/40 benchmark: ${percent(benchmark.simulation.probability_objective, 0)}.` : "No mix meets the mandate." })}
    </div>
    <div style="margin-top:18px">${stopBanner(data.stop_condition, "process")}</div>
    <section class="section"><h2>The evidence</h2>
      <div class="grid cols-3" style="margin-top:16px">
        <div class="card stack"><p class="group-title">Efficient frontier</p>
          <div style="font-size:30px;font-weight:800">${count(meeting)} of ${count(data.frontier.length)}</div>
          <p class="muted">possible mixes meet every mandate rule and the objective. The target is barely reachable.</p>
          <a href="#/institution/frontier">See the frontier →</a></div>
        <div class="card stack"><p class="group-title">Will the money last?</p>
          <div style="font-size:30px;font-weight:800">${plan ? percent(plan.simulation.probability_below_90m, 0) : "—"}</div>
          <p class="muted">chance the optimizer's portfolio dips below $90 million within seven years
            (60/40 benchmark: ${percent(benchmark.simulation.probability_below_90m, 0)}).</p>
          <a href="#/institution/lasting">See the simulation →</a></div>
        <div class="card stack"><p class="group-title">Would it have worked?</p>
          <div style="font-size:30px;font-weight:800">${moneyShort(backtest["Constrained portfolio"]?.ending_dollar_value)}</div>
          <p class="muted">is what $100 million became under the optimizer since 2011, against
            ${moneyShort(backtest["60/40 benchmark"]?.ending_dollar_value)} for the plain 60/40 benchmark.</p>
          <a href="#/institution/worked">See the backtest →</a></div>
      </div>
    </section>
    <section class="section"><h2>Recommendation</h2><div style="margin-top:16px">${recommendationHtml(data.recommendation)}</div></section>`;
}

function mandate(data) {
  const rules = data.mandate_rules.map((rule) => `<li>${escapeHtml(rule)}</li>`).join("");
  const order = ["Constrained portfolio", "60/40 benchmark", "Equal weight"];
  const cards = order.map((name) => named(data, name)).filter(Boolean).map((portfolio) => (
    portfolio.weights ? portfolioCard(portfolio, {
      title: label(portfolio.name),
      rows: FUNDS.filter((fund) => portfolio.weights[fund] > 0).map((fund) => [`${fund} in dollars`, money(portfolio.dollars[fund])]),
    }) : `<div class="card"><h3>${dot(portfolio.name)} ${escapeHtml(label(portfolio.name))}</h3><p class="muted" style="margin-top:8px">No mix meets the mandate.</p></div>`
  )).join("");
  return `<h1 style="font-size:40px">Mandate and compliance</h1>
    <p class="muted" style="margin-top:8px">The rules come first. Every portfolio is checked against the same ones.</p>
    <section class="section"><h2>The rules</h2><div class="document" style="margin-top:14px"><ul style="margin:0;padding-left:20px">${rules}</ul></div></section>
    <section class="section"><h2>Three portfolios, one rulebook</h2>
      <p class="lede">Two transparent baselines and the constrained portfolio: the lowest-risk mix that meets every rule.</p>
      <div class="grid cols-3">${cards}</div></section>`;
}

function signal(data) {
  const info = data.cpi_signal;
  return `<h1 style="font-size:40px">Inflation signal</h1>
    <p class="muted" style="margin-top:8px">The objective is inflation plus ${percent(data.mandate.objective_spread, 0)}, so the
      inflation number matters. Compass uses the figure as it was known on the decision date, not today's revised one.</p>
    <div class="grid cols-3" style="margin-top:24px">
      ${metricCard({ label: "Inflation as known", value: percent(info.inflation), note: "Consumer Price Index, change from a year earlier." })}
      ${metricCard({ label: "Latest month known", value: monthName(info.month), medium: true, note: `On the decision date, ${dateLong(info.decision_date)}.` })}
      ${metricCard({ label: "First published", value: dateLong(info.first_publication_date), medium: true, note: "Checked against the archive of past data releases." })}
    </div>
    <section class="section"><h2>Data card: Consumer Price Index</h2><div class="document" style="margin-top:14px">${markdown(data.data_card.cpi)}</div></section>
    <section class="section"><h2>Data card: fund returns</h2><div class="document" style="margin-top:14px">${markdown(data.data_card.prices)}</div></section>`;
}

function frontierSection(data) {
  const meeting = data.frontier.filter((mix) => mix.meets_mandate).length;
  return `<h1 style="font-size:40px">Efficient frontier</h1>
    <p class="muted" style="margin-top:8px">Every possible mix of the four funds in 5-point steps, plotted by risk and return.</p>
    <div class="card" style="margin-top:24px">
      <div class="chart tall" id="chart-frontier"></div>
      <p class="caption">Each dot is one of ${count(data.frontier.length)} mixes. Only ${count(meeting)} (in green) meet every
        rule and the objective, shown by the dashed line. The diamonds are the three portfolios.</p>
    </div>`;
}

function lasting(data) {
  const rows = ["Constrained portfolio", "60/40 benchmark", "Equal weight"].map((name) => named(data, name))
    .filter((portfolio) => portfolio?.simulation).map((portfolio) => [
      `${dot(portfolio.name)} ${escapeHtml(label(portfolio.name))}`,
      percent(portfolio.simulation.probability_objective, 1), percent(portfolio.simulation.probability_below_90m, 1),
      money(portfolio.simulation.median_ending_value), money(portfolio.simulation.p5_ending_value),
      money(portfolio.simulation.p95_ending_value),
    ]);
  const options = data.portfolios.filter((portfolio) => portfolio.fan_chart_bands)
    .map((portfolio) => `<option value="${escapeHtml(portfolio.name)}">${escapeHtml(label(portfolio.name))}</option>`).join("");
  return `<h1 style="font-size:40px">Will the money last?</h1>
    <p class="muted" style="margin-top:8px">Ten thousand simulated seven-year paths for the $100 million, paying out
      ${money(data.mandate.cash_flow_amount)} every quarter. Each simulated month is a real month drawn from history.</p>
    <div class="card" style="margin-top:24px">
      <label class="field no-print" style="max-width:340px">Portfolio to show
        <select class="input" id="fan-select">${options}</select></label>
      <div class="chart tall" id="chart-fan" style="margin-top:12px"></div>
      <p class="caption">The bands hold the middle half and the middle 90% of outcomes. The dashed line marks $90 million.</p>
    </div>
    <div class="card" style="margin-top:18px">${table([{ label: "Portfolio" }, { label: "Chance of meeting the objective", num: true },
    { label: "Chance of dipping below $90 million", num: true }, { label: "Median ending value", num: true },
    { label: "Poor outcome (5th percentile)", num: true }, { label: "Strong outcome (95th percentile)", num: true }], rows)}</div>`;
}

function worked(data) {
  const rows = data.backtest.table.map((row) => [
    `${dot(row.portfolio)} ${escapeHtml(label(row.portfolio))}`, percent(row.annualized_return), percent(row.volatility),
    percent(row.worst_peak_to_trough_drop), money(row.ending_dollar_value), String(row.objective_not_reachable_months),
    percent(row.average_turnover),
  ]);
  const months = data.backtest.monthly_series["Constrained portfolio"];
  return `<h1 style="font-size:40px">Would it have worked?</h1>
    <p class="muted" style="margin-top:8px">A point-in-time backtest from ${monthName(months[0].month)} to
      ${monthName(months[months.length - 1].month)}. Each month the mix is chosen using only returns and inflation known
      on that day, then held for the next month, after trading costs of ${settings.backtest_cost ?? 10} basis points on
      each trade and the quarterly payouts. Change the cost in the Stress lab.</p>
    <div class="card" style="margin-top:24px">
      <div class="chart tall" id="chart-worked"></div>
      <p class="caption">What $100 million became under each approach. A test with hindsight would look better; this one has none.</p>
    </div>
    <div class="card" style="margin-top:18px">${table([{ label: "Portfolio" }, { label: "Return per year", num: true },
    { label: "Volatility", num: true }, { label: "Worst drop", num: true }, { label: "Ending value", num: true },
    { label: "Months objective out of reach", num: true }, { label: "Average monthly turnover", num: true }], rows)}</div>
    <div class="card" style="margin-top:18px">
      <h3>How the optimizer's mix changed over time</h3>
      <div class="chart" id="chart-weights"></div>
      <p class="caption">The optimizer swings between funds as its estimates change. That churn is the instability the stop condition measures.</p>
    </div>`;
}

function stress(data) {
  const current = {
    cap_on: settings.cap_on ?? true,
    reserve_minimum: settings.reserve_minimum ?? data.mandate.minimum_reserve_weight,
    objective_spread: settings.objective_spread ?? data.mandate.objective_spread,
    estimate_window: settings.estimate_window ?? "all history",
    stop_threshold: settings.stop_threshold ?? data.stop_condition.threshold,
    backtest_cost: settings.backtest_cost ?? 10,
  };
  const windows = ["all history", "last 60 months", "last 36 months"].map((option) => (
    `<option ${option === current.estimate_window ? "selected" : ""}>${option}</option>`)).join("");
  return `<h1 style="font-size:40px">Stress lab</h1>
    <p class="muted" style="margin-top:8px">Change one assumption at a time and see whether the recommended mix survives.</p>
    <form class="card no-print" id="stress-form" style="margin-top:24px">
      <div class="grid cols-4">
        <label class="field">60% cap on any one fund
          <select class="input" name="cap_on"><option value="true" ${current.cap_on ? "selected" : ""}>On</option>
          <option value="false" ${current.cap_on ? "" : "selected"}>Off</option></select></label>
        <label class="field">Reserve minimum (%)
          <input class="input" name="reserve_minimum" type="number" min="0" max="100" step="1" value="${Math.round(current.reserve_minimum * 100)}"></label>
        <label class="field">Objective: inflation plus (%)
          <input class="input" name="objective_spread" type="number" min="0" max="15" step="0.5" value="${(current.objective_spread * 100).toFixed(1)}"></label>
        <label class="field">Estimate window
          <select class="input" name="estimate_window">${windows}</select></label>
        <label class="field">Stop threshold (points)
          <input class="input" name="stop_threshold" type="number" min="5" max="100" step="5" value="${Math.round(current.stop_threshold * 100)}"></label>
        <label class="field">Trading cost in the backtest (basis points)
          <input class="input" name="backtest_cost" type="number" min="0" max="200" step="5" value="${current.backtest_cost}"></label>
        <div style="display:flex;align-items:flex-end;gap:10px">
          <button class="button small" type="submit">Run stress lab</button>
          <button class="button ghost small" type="button" id="stress-reset">Reset</button></div>
      </div>
    </form>
    <details class="card funds no-print" style="margin-top:18px" ${institutionUniverse.custom ? "open" : ""}>
      <summary>Funds and stocks the foundation may hold <span class="muted" style="font-weight:400">(${institutionUniverse.custom ? `${institutionUniverse.universe.length} holdings` : "the four core funds, as graded"})</span></summary>
      <div id="institution-universe" style="margin-top:12px"></div>
      <div style="display:flex;gap:10px;margin-top:12px;flex-wrap:wrap">
        <button class="button small" type="button" id="universe-apply">Run with these holdings</button>
        <button class="button ghost small" type="button" id="universe-reset">Back to the four core funds</button>
      </div>
      <p class="caption">With individual stocks, the diversification rules switch on: at most 10% in any one stock, at most
        40% in stocks in total, and at least 5 holdings of 2% or more when there are 8 or more.</p>
    </details>
    <div style="margin-top:18px">${stopBanner(data.stop_condition, "process")}</div>
    <p class="caption">The stop condition was set before looking at results: stop if the base case has no mix, or if any
      single change moves a fund's weight by more than ${points(data.stop_condition.threshold)}.</p>
    <div style="margin-top:18px">${stressTables(data.stress, data.stop_condition)}</div>`;
}

function parseLockedRun(lines) {
  const blocks = { before: {}, after: {} };
  let current = null;
  for (const raw of lines ?? []) {
    const line = raw.trim();
    if (line.startsWith("BASE")) current = blocks.before;
    else if (line.startsWith("CHANGED")) current = blocks.after;
    if (!current) continue;
    const header = /VT expected return ([\d.]+%)/.exec(line);
    if (header) current.vt = header[1];
    if (line.startsWith("constrained portfolio:")) {
      const mix = /\{'SGOV': (\d+), 'IEF': (\d+), 'USIG': (\d+), 'VT': (\d+)\}/.exec(line);
      current.mix = mix ? `SGOV ${mix[1]}% · IEF ${mix[2]}% · USIG ${mix[3]}% · VT ${mix[4]}%` : "No mix meets the mandate";
    }
    const row = /^(.*?): chance of objective ([\d.]+%), below \$90M ([\d.]+%), median \$([\d.]+)M/.exec(line);
    if (row) (current.rows ??= []).push({ name: row[1], chance: row[2], below: row[3], median: `$${row[4]} million` });
  }
  return blocks;
}

function locked(data) {
  const record = data.locked_record;
  const run = parseLockedRun(record.result_lines);
  const prediction = String(record.prediction ?? "").replace(/^>\s?/gm, "").replace(/\s*-\s*$/, "").trim();
  const rows = [
    ["VT expected return (the changed input)", run.before.vt ?? record.old_value, run.after.vt ?? record.new_value],
    ["Optimizer's mix", run.before.mix ?? "—", run.after.mix ?? "—"],
  ];
  (run.before.rows ?? []).forEach((row, index) => {
    const after = run.after.rows?.[index];
    const name = row.name.replace("Constrained (base mix)", "Optimizer's original mix");
    rows.push([`${name}: chance of meeting the objective`, row.chance, after?.chance ?? "—"]);
    rows.push([`${name}: chance of dipping below $90 million`, row.below, after?.below ?? "—"]);
  });
  return `<h1 style="font-size:40px">Locked prediction</h1>
    <p class="muted" style="margin-top:8px">One input was changed. The prediction was written without artificial intelligence
      and committed to GitHub before the run.</p>
    <section class="section"><h2>The prediction</h2>
      <div class="document" style="margin-top:14px">
        <p class="group-title">Locked ${escapeHtml(record.lock_date)} · before the run</p>
        <blockquote style="margin:10px 0 0;padding:12px 18px;border-left:4px solid var(--accent);background:var(--accent-soft);border-radius:0 10px 10px 0">${escapeHtml(prediction)}</blockquote>
      </div></section>
    <section class="section"><h2>What happened</h2>
      <div class="card" style="margin-top:14px">${table([{ label: "" }, { label: "Before", num: true }, { label: "After the change", num: true }],
    rows.map(([name, before, after]) => [escapeHtml(name), escapeHtml(before), `<strong>${escapeHtml(after)}</strong>`]))}
        <details class="more"><summary>Raw output of the run</summary><pre class="raw">${escapeHtml(record.locked_run_raw_text)}</pre></details>
      </div></section>`;
}

function committee(data) {
  return `<h1 style="font-size:40px">Committee review</h1>
    <p class="muted" style="margin-top:8px">Three investors with different philosophies review the same computed facts about the optimizer.</p>
    <div id="committee-body" style="margin-top:24px">${committeeHtml(data.committee)}</div>`;
}

function report(data) {
  const plan = planOf(data);
  const cards = ["Constrained portfolio", "60/40 benchmark", "Equal weight"].map((name) => named(data, name))
    .filter((portfolio) => portfolio?.weights).map((portfolio) => portfolioCard(portfolio, { title: label(portfolio.name) })).join("");
  const votes = (data.committee?.members ?? []).map((member) => `<div class="kv"><span>${escapeHtml(member.name)}</span><span>${escapeHtml(member.vote)}</span></div>`).join("");
  return `<h1 style="font-size:34px">${escapeHtml(data.mandate.name)}: committee report</h1>
    <p class="muted" style="margin-top:6px">Decision date ${dateLong(data.cpi_signal.decision_date)} · inflation as known ${percent(data.cpi_signal.inflation)}
      · objective ${percent(data.cpi_signal.inflation + data.mandate.objective_spread)}</p>
    <div style="margin-top:16px">${stopBanner(data.stop_condition, "process")}</div>
    <section class="section"><h2>Portfolios and mandate verdicts</h2><div class="grid cols-3" style="margin-top:12px">${cards}</div></section>
    ${plan ? `<section class="section"><h2>Allocation of the constrained portfolio</h2><div class="card" style="margin-top:12px">${weightBar(plan.weights)}<div style="margin-top:10px">${fundLegend(plan.weights, plan.dollars)}</div></div></section>` : ""}
    ${votes ? `<section class="section"><h2>Committee votes: ${escapeHtml(data.committee.outcome ?? "")}</h2><div class="card" style="margin-top:12px">${votes}</div></section>` : ""}
    <section class="section"><h2>Recommendation</h2><div style="margin-top:12px">${recommendationHtml(data.recommendation)}</div></section>`;
}

const RENDERERS = { summary, mandate, signal, frontier: frontierSection, lasting, worked, stress, locked, committee, report };

/* ------------------------------------------------------------------ page */

/** Short facts about the foundation run so Ask Compass knows what the page shows. */
function institutionContext(data) {
  const plan = planOf(data);
  const benchmark = named(data, "60/40 benchmark");
  const signal = data.cpi_signal;
  const lines = [
    `${data.mandate.name}: ${moneyShort(data.mandate.portfolio_size_dollars)}, payout ${money(data.mandate.cash_flow_amount)} a quarter, ${data.mandate.horizon_years} years`,
    `Inflation as known: ${percent(signal.inflation)} (${monthName(signal.month)}); objective ${percent(signal.inflation + data.mandate.objective_spread)}`,
  ];
  for (const portfolio of data.portfolios) {
    if (!portfolio.weights) continue;
    lines.push(`${portfolio.name}: ${mixText(portfolio.weights)}; expected return ${percent(portfolio.expected_return)}; volatility ${percent(portfolio.volatility)}; chance of meeting the objective ${percent(portfolio.simulation?.probability_objective, 1)}`);
  }
  for (const row of data.backtest?.table ?? []) lines.push(`Backtest ${row.portfolio}: ending value ${moneyShort(row.ending_dollar_value)}`);
  if (data.stop_condition) lines.push(`Stop condition triggered: ${data.stop_condition.triggered ? "yes" : "no"}`);
  if (data.committee?.outcome) lines.push(`Committee outcome: ${data.committee.outcome}`);
  if (data.improved_forecast?.chance_of_meeting_objective != null) {
    lines.push(`Improved forecast: chance of keeping at least ${moneyShort(data.mandate.portfolio_size_dollars)} after payouts: ${percent(data.improved_forecast.chance_of_meeting_objective, 1)}`);
  }
  if (benchmark && !plan) lines.push("No mix meets the mandate in this run.");
  return lines;
}

export async function renderInstitution(root, section, navigate) {
  const active = RENDERERS[section] ? section : "summary";
  const menu = SECTIONS.map(([id, name]) => (
    `<a href="#/institution/${id}" class="${id === active ? "active" : ""}">${name}</a>`)).join("");
  root.innerHTML = `<div class="page"><div class="with-menu">
    <nav class="menu no-print" aria-label="Sections"><div class="menu-title">Institution</div>${menu}</nav>
    <div id="institution-body">${skeleton("Running 10,000 simulations and an 18-year point-in-time backtest...", 360)}</div>
  </div></div>`;
  const body = root.querySelector("#institution-body");

  let data;
  try {
    data = await getInstitution({ ...settings, ...universeSettings() });
  } catch (error) {
    body.innerHTML = errorCard(error.message);
    return;
  }
  if (!body.isConnected) return; // the person moved on while this was loading
  registerFunds(data.universe?.funds ?? []);
  body.innerHTML = RENDERERS[active](data);
  setAssistantContext(`Institution: ${SECTIONS.find(([id]) => id === active)?.[1] ?? active}`, institutionContext(data), [
    "Why does the committee vote the way it does?",
    "Explain the stop condition",
    "Explain the chance of meeting the objective",
  ]);
  if (institutionUniverse.custom && active !== "stress") {
    body.insertAdjacentHTML("afterbegin", `<div class="banner info no-print" style="margin-bottom:18px"><span>i</span>
      <span>Showing a custom set of ${institutionUniverse.universe.length} holdings, not the graded four-fund run.
      <a href="#/institution/stress">Change it in the Stress lab.</a></span></div>`);
  }

  if (active === "frontier") {
    charts.frontier(body.querySelector("#chart-frontier"), data.frontier, data.portfolios,
      data.cpi_signal.inflation + (settings.objective_spread ?? data.mandate.objective_spread));
  }
  if (active === "lasting") {
    const select = body.querySelector("#fan-select");
    const drawFan = () => {
      const portfolio = named(data, select.value);
      charts.fan(body.querySelector("#chart-fan"), portfolio.fan_chart_bands,
        { low: "p5", lowMid: "p25", mid: "median", highMid: "p75", high: "p95" },
        { value: 90_000_000, label: "$90 million" }, PORTFOLIO_COLORS[portfolio.name]);
    };
    if (planOf(data)) select.value = "Constrained portfolio";
    select.addEventListener("change", drawFan);
    drawFan();
  }
  if (active === "worked") {
    const series = {};
    for (const name of ["Constrained portfolio", "60/40 benchmark", "Equal weight"]) {
      if (data.backtest.monthly_series[name]) series[name] = data.backtest.monthly_series[name];
    }
    charts.valueLines(body.querySelector("#chart-worked"), series);
    charts.weightAreas(body.querySelector("#chart-weights"), data.backtest.monthly_series["Constrained portfolio"]);
  }
  if (active === "stress") {
    const form = body.querySelector("#stress-form");
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const values = new FormData(form);
      settings = {
        cap_on: values.get("cap_on") === "true",
        reserve_minimum: Number(values.get("reserve_minimum")) / 100,
        objective_spread: Number(values.get("objective_spread")) / 100,
        estimate_window: values.get("estimate_window"),
        stop_threshold: Number(values.get("stop_threshold")) / 100,
        backtest_cost: Number(values.get("backtest_cost")),
      };
      renderInstitution(root, "stress", navigate);
    });
    body.querySelector("#stress-reset").addEventListener("click", () => {
      settings = {};
      renderInstitution(root, "stress", navigate);
    });
    const draft = { universe: institutionUniverse.universe.map((fund) => ({ ...fund })) };
    renderUniverseEditor(body.querySelector("#institution-universe"), draft);
    body.querySelector("#universe-apply").addEventListener("click", () => {
      institutionUniverse.universe = draft.universe;
      institutionUniverse.custom = !isDefaultUniverse(draft.universe);
      renderInstitution(root, "stress", navigate);
    });
    body.querySelector("#universe-reset").addEventListener("click", () => {
      institutionUniverse.universe = DEFAULT_UNIVERSE.map((fund) => ({ ...fund }));
      institutionUniverse.custom = false;
      renderInstitution(root, "stress", navigate);
    });
  }
  if (active === "committee") {
    const committeeBody = body.querySelector("#committee-body");
    const wire = () => attachLiveReview(committeeBody, { mode: "institution", settings }, (result, model) => {
      committeeBody.innerHTML = committeeHtml(result, model);
      wire();
    });
    wire();
  }
  if (active === "report") {
    setTimeout(() => window.print(), 400);
  }
}
