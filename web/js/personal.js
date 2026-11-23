// Personal mode: the home page with the plan form, and the plan results page.
import { postPersonalPlan } from "./api.js";
import * as charts from "./charts.js";
import { attachLiveReview, committeeHtml } from "./committee.js";
import {
  FUNDS, PORTFOLIO_COLORS, escapeHtml, mixText, money, moneyShort, parseMoney, percent, verdictSentence, weight,
} from "./format.js";
import {
  chip, errorCard, fundLegend, metricCard, portfolioCard, skeleton, stopBanner, stressTables, table,
} from "./ui.js";
import { registerFunds } from "./format.js";
import { DEFAULT_UNIVERSE, isDefaultUniverse, renderUniverseEditor, universeForRequest } from "./universe.js";
import { screensHtml } from "./screens.js";
import { explainButton, setAssistantContext } from "./assistant.js";

const STORAGE_KEY = "compass.personal.inputs.v2";

export const DEFAULT_INPUTS = {
  savings: 40000,
  monthly_contribution: 1200,
  goal: 1000000,
  years: 30,
  tolerated_drop: 0.40,
  monthly_expenses: 3000,
  reserve_months: 6,
};

export function loadInputs() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
    if (saved && saved.goal >= 1000) return { ...DEFAULT_INPUTS, ...saved };
  } catch (error) {
    // fall through to the defaults
  }
  return { ...DEFAULT_INPUTS };
}

export function saveInputs(inputs) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(inputs));
}

/** The service accepts holdings as an object keyed by fund, or nothing. */
function cleanInputs(raw) {
  const inputs = {
    savings: Number(raw.savings),
    monthly_contribution: Number(raw.monthly_contribution),
    goal: Number(raw.goal),
    years: Math.round(Number(raw.years)),
    tolerated_drop: Number(raw.tolerated_drop),
    monthly_expenses: Number(raw.monthly_expenses),
    reserve_months: Math.round(Number(raw.reserve_months)),
  };
  const universe = universeForRequest(raw.universe);
  if (universe) {
    inputs.universe = universe;
    // Diversification rules switch on automatically once the plan holds individual stocks.
    if (universe.some((fund) => fund.role === "individual stock")) {
      inputs.max_single_stock_weight = 0.10;
      inputs.max_individual_stocks_total = 0.40;
      if (universe.length >= 8) inputs.min_holdings = 5;
    }
  }
  if (raw.holdings) {
    const tickers = (raw.universe ?? DEFAULT_UNIVERSE).map((fund) => fund.ticker);
    const holdings = Array.isArray(raw.holdings)
      ? Object.fromEntries(tickers.map((fund, index) => [fund, Number(raw.holdings[index] ?? 0)]))
      : raw.holdings;
    if (tickers.some((fund) => Number(holdings[fund] ?? 0) > 0) || Number(raw.other_cash ?? 0) > 0) {
      inputs.holdings = Object.fromEntries(tickers.map((fund) => [fund, Number(holdings[fund] ?? 0)]));
      inputs.other_cash = Number(raw.other_cash ?? 0);
    }
  }
  return inputs;
}

/** The tickers a plan response is about. */
function planTickers(data) {
  const funds = data.universe?.funds;
  return funds?.length ? funds.map((fund) => fund.ticker) : FUNDS;
}

/* ------------------------------------------------------------------ home page */

const ICONS = {
  rules: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 11l2 2 4-4"/><rect x="4" y="3" width="16" height="18" rx="3"/></svg>',
  odds: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 20c4-1 6-6 9-9s5-5 9-6"/><path d="M3 20c5 0 8-2 11-4s5-2 7-2" opacity=".5"/></svg>',
  honest: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
};

function moneyField(name, label, value, hint = "") {
  return `<label class="field">${label}${hint ? `<span class="hint">${hint}</span>` : ""}
    <input class="input" name="${name}" inputmode="numeric" autocomplete="off" data-money value="${money(value)}"></label>`;
}

export function renderHome(root, navigate) {
  const inputs = loadInputs();
  root.innerHTML = `<div class="page">
    <section class="hero">
      <div>
        <span class="eyebrow">Personal mode</span>
        <h1>An investment committee in your pocket</h1>
        <p class="lede">Tell Compass your goal. It writes your rules, picks the lowest-risk mix that can get you there,
          shows your odds, and tests the plan the way a professional committee would.</p>
      </div>
      <form class="card stack" id="plan-form" novalidate>
        <h3>Build your plan</h3>
        <div class="form-grid">
          ${moneyField("savings", "Current savings", inputs.savings, "Money you have saved or invested today.")}
          ${moneyField("monthly_contribution", "Monthly contribution", inputs.monthly_contribution, "How much you will put into investments each month, not your income.")}
          ${moneyField("goal", "Goal, in today's dollars", inputs.goal, "What you want to have, in what money buys today.")}
          <label class="field">Years to the goal
            <input class="input" name="years" type="number" min="1" max="60" step="1" value="${inputs.years}"></label>
          ${moneyField("monthly_expenses", "Monthly expenses", inputs.monthly_expenses, "Only used to size your emergency cash. Expenses are not taken out of your investments.")}
          <label class="field">Months of emergency reserve: <span data-show="reserve_months">${inputs.reserve_months}</span>
            <input name="reserve_months" type="range" min="0" max="12" step="1" value="${inputs.reserve_months}"></label>
          <label class="field wide">Largest one-year drop you could live with:
            <span data-show="tolerated_drop">${weight(inputs.tolerated_drop)}</span>
            <input name="tolerated_drop" type="range" min="5" max="60" step="5" value="${Math.round(inputs.tolerated_drop * 100)}"></label>
        </div>
        <details class="funds" ${isDefaultUniverse(inputs.universe) ? "" : "open"}>
          <summary>Choose your funds and stocks <span class="muted" style="font-weight:400" data-universe-count></span></summary>
          <div id="universe-editor" style="margin-top:10px"></div>
        </details>
        <div id="form-error"></div>
        <button class="button block" type="submit">Build my plan</button>
        <p class="caption">Starts from four low-cost funds (Treasury bills, government bonds, corporate bonds, global
          stocks). Add up to 15 funds or individual stocks, or start from Warren Buffett's portfolio on the Legends page.</p>
      </form>
    </section>

    <section class="section">
      <div class="grid cols-3">
        <div class="card feature">${ICONS.rules}<h3>Rules first</h3>
          <p>Your plan becomes a written policy with pass or fail checks, the way a foundation's does.</p></div>
        <div class="card feature">${ICONS.odds}<h3>Odds, not promises</h3>
          <p>Ten thousand simulations of your savings show how likely you are to reach the goal.</p></div>
        <div class="card feature">${ICONS.honest}<h3>Tested honestly</h3>
          <p>Every past decision uses only what was known that day, including inflation before it was revised.</p></div>
      </div>
    </section>

    <section class="section">
      <h2>How it works</h2>
      <div class="grid cols-3 steps" style="margin-top:18px">
        <div class="card step"><div><h3>Set your goal</h3><p class="muted">Savings, contributions, the goal, your
          time frame and how big a loss you could sit through.</p></div></div>
        <div class="card step"><div><h3>See the plan and the odds</h3><p class="muted">The lowest-risk mix that is
          expected to reach the goal, next to two simple baselines.</p></div></div>
        <div class="card step"><div><h3>Stress it, then act</h3><p class="muted">A stress test, a committee review,
          and the exact dollars to buy or sell today.</p></div></div>
      </div>
    </section>
  </div>`;

  const form = root.querySelector("#plan-form");
  const universeState = { universe: (inputs.universe ?? DEFAULT_UNIVERSE).map((fund) => ({ ...fund })) };
  registerFunds(universeState.universe);
  const showCount = () => {
    form.querySelector("[data-universe-count]").textContent = isDefaultUniverse(universeState.universe)
      ? "(the four core funds)" : `(${universeState.universe.length} holdings)`;
  };
  renderUniverseEditor(form.querySelector("#universe-editor"), universeState, showCount);
  showCount();
  form.querySelectorAll("[data-money]").forEach((field) => {
    field.addEventListener("blur", () => { field.value = money(parseMoney(field.value)); });
    field.addEventListener("focus", () => field.select());
  });
  form.querySelector('[name="reserve_months"]').addEventListener("input", (event) => {
    form.querySelector('[data-show="reserve_months"]').textContent = event.target.value;
  });
  form.querySelector('[name="tolerated_drop"]').addEventListener("input", (event) => {
    form.querySelector('[data-show="tolerated_drop"]').textContent = `${event.target.value}%`;
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const next = {
      savings: parseMoney(data.get("savings")),
      monthly_contribution: parseMoney(data.get("monthly_contribution")),
      goal: parseMoney(data.get("goal")),
      years: Number(data.get("years")),
      tolerated_drop: Number(data.get("tolerated_drop")) / 100,
      monthly_expenses: parseMoney(data.get("monthly_expenses")),
      reserve_months: Number(data.get("reserve_months")),
      universe: isDefaultUniverse(universeState.universe) ? undefined : universeState.universe,
    };
    const problem = next.goal <= 0 ? "Enter a goal above $0."
      : !(next.years >= 1 && next.years <= 60) ? "Years to the goal must be between 1 and 60." : "";
    if (problem) {
      form.querySelector("#form-error").innerHTML = `<div class="banner bad"><span>✕</span><span>${problem}</span></div>`;
      return;
    }
    saveInputs(next);
    navigate("#/personal/plan");
  });
}

/* ------------------------------------------------------------------ results page */

const SECTIONS = [
  ["summary", "Summary"], ["safety", "Safety net"], ["allocation", "Allocation"], ["odds", "Will I make it?"],
  ["history", "If you had started"], ["fragile", "How fragile is this?"], ["today", "What to do today"],
  ["policy", "Policy statement"], ["committee", "Committee review"],
];

function chanceTone(chance) {
  if (chance >= 0.75) return "good";
  if (chance >= 0.5) return "caution";
  return "bad";
}

function summaryHtml(data, plan) {
  const objective = data.objective;
  const chance = plan?.simulation?.chance_of_goal;
  const needed = data.contribution_for_80_percent;
  const neededIsNumber = typeof needed === "number";
  const cards = [
    plan ? metricCard({
      label: "Chance of reaching the goal",
      value: percent(chance, 0),
      tone: chanceTone(chance),
      note: chance < 0.5
        ? "A plan that is only expected to reach the goal misses it more often than not, because bad years hurt more than good years help."
        : "Share of 10,000 simulated futures that end at or above your goal.",
    }) : metricCard({
      label: "Chance of reaching the goal", value: "No plan yet", tone: "bad", medium: true,
      note: "No mix of the four funds meets your rules. See the ways to make it work below.",
    }),
    metricCard({
      label: "Return your plan needs",
      value: objective.required_return == null ? "Not reachable" : percent(objective.required_return),
      medium: objective.required_return == null,
      note: objective.required_real_return == null ? "Even a very high return would not reach this goal."
        : `${percent(objective.required_real_return)} above inflation, plus inflation of ${percent(objective.inflation)} as known on the decision date.`,
    }),
    metricCard({
      label: "Monthly contribution for an 80% chance",
      value: neededIsNumber ? money(needed) : "Not known",
      medium: !neededIsNumber,
      note: neededIsNumber ? `You plan to add ${money(data.inputs.monthly_contribution)} a month, with the same mix.` : "Needs a plan first.",
      extra: neededIsNumber && Math.round(needed) !== Math.round(data.inputs.monthly_contribution)
        ? `<button class="button small no-print" type="button" data-rebuild-contribution="${needed}">Rebuild with this contribution</button>` : "",
    }),
  ];
  return `<div class="grid cols-3">${cards.join("")}</div>`;
}

function safetyHtml(reserve, inputs) {
  const shortfall = reserve.shortfall > 0;
  const fundNote = shortfall
    ? (reserve.months_to_fund == null ? "With no monthly contribution, the reserve cannot be filled."
      : `Your first ${reserve.months_to_fund} monthly contributions fill the reserve before any investing starts.`)
    : "Fully funded from your savings today.";
  return `<div class="grid cols-3">
    ${metricCard({ label: "Reserve target", value: money(reserve.reserve_target), medium: true, note: `${inputs.reserve_months} months of ${money(inputs.monthly_expenses)} expenses, kept in cash outside the plan.` })}
    ${metricCard({ label: "Set aside now", value: money(reserve.amount_set_aside_now), medium: true, tone: shortfall ? "caution" : "good", note: fundNote })}
    ${metricCard({ label: "Invested in the plan", value: money(reserve.invested_starting_amount), medium: true, note: "Savings left after the reserve. Only this money counts toward the goal." })}
  </div>`;
}

function waysHtml(ways) {
  const cards = ways.map((way, index) => {
    const reachable = way.result !== "not reachable" && way.result !== "already works";
    const works = way.result === "already works";
    let headline = "Not reachable this way";
    if (works) headline = "Already works";
    else if (reachable && /contribution/i.test(way.change)) headline = `${money(way.result)} a month`;
    else if (reachable && /year/i.test(way.change)) headline = `${way.result} more ${Number(way.result) === 1 ? "year" : "years"}`;
    else if (reachable) headline = `A ${weight(way.result)} drop limit`;
    return `<div class="card stack">
      <p class="group-title">${escapeHtml(way.change)}</p>
      <div style="font-size:26px;font-weight:800">${escapeHtml(headline)}</div>
      <p class="muted" style="font-size:14px">${escapeHtml(way.explanation ?? "")}</p>
      ${reachable ? `<button class="button small no-print" type="button" data-way="${index}">Rebuild with this change</button>` : ""}
    </div>`;
  });
  return `<div class="grid cols-3">${cards.join("")}</div>`;
}

function allocationHtml(data, plan, baselines) {
  const baselineCards = baselines.map((portfolio) => portfolioCard(portfolio, {
    rows: [["Chance of the goal", percent(portfolio.simulation?.chance_of_goal, 0)],
      ["Worst 12-month return", percent(portfolio.worst_12_month_return)]],
  })).join("");
  if (!plan) {
    return `<div class="banner bad"><span>✕</span><span>No mix of the four funds meets every rule.
      <span class="detail">Either the return you need is higher than these funds are expected to earn, or the drop limit
      rules out the mixes that could earn it. Each card below changes one thing.</span></span></div>
      <div style="margin-top:18px">${waysHtml(data.ways_to_make_it_work)}</div>
      <h3 style="margin-top:28px">The two baselines, for comparison</h3>
      <div class="grid cols-2" style="margin-top:12px">${baselineCards}</div>`;
  }
  return `<div class="grid cols-2">
      <div class="card">
        <h3><span class="dot" style="background:${PORTFOLIO_COLORS["Your plan"]}"></span> Your plan</h3>
        <div class="chart" id="personal-donut" style="height:300px"></div>
        ${fundLegend(plan.weights, plan.dollars)}
      </div>
      <div class="card stack">
        <h3>Does it pass your rules?</h3>
        <div>
          <div class="kv"><span>Expected return</span><span>${percent(plan.expected_return)} a year</span></div>
          <div class="kv"><span>Volatility</span><span>${percent(plan.volatility)}</span></div>
          <div class="kv"><span>Worst 12-month return in the history</span><span>${percent(plan.worst_12_month_return)}</span></div>
        </div>
        <div class="chips">${plan.verdicts.map((verdict) => verdictLine(verdict)).join("")}</div>
        <p class="caption">This is the lowest-risk mix, in 5-point steps, that meets every rule.</p>
      </div>
    </div>
    <h3 style="margin-top:28px">Two simple baselines, checked against the same rules</h3>
    <div class="grid cols-2" style="margin-top:12px">${baselineCards}</div>`;
}

function verdictLine(verdict) {
  return chip(verdict.pass ? "pass" : "fail", verdictSentence(verdict));
}

function oddsHtml(plan, data) {
  if (!plan) return `<div class="card"><p class="muted">The simulation needs a plan first.</p></div>`;
  const simulation = plan.simulation;
  return `<div class="card">
      <div class="chart tall" id="personal-fan"></div>
      <p class="caption">Ten thousand possible futures for your savings, in today's dollars. The shaded bands hold the
        middle half and the middle 80% of outcomes; the dashed line is your goal.</p>
    </div>
    <div class="grid cols-3" style="margin-top:18px">
      ${metricCard({ label: "Poor outcome (1 in 10 is worse)", value: moneyShort(simulation.p10_ending_value), medium: true })}
      ${metricCard({ label: "Median outcome", value: moneyShort(simulation.median_ending_value), medium: true, note: `Your goal is ${money(data.inputs.goal)}.` })}
      ${metricCard({ label: "Strong outcome (1 in 10 is better)", value: moneyShort(simulation.p90_ending_value), medium: true })}
    </div>
    ${improvedHtml(plan, data)}`;
}

/** Second opinion from the improved forecast (12-month blocks, today's yields, uncertain averages). */
function improvedHtml(plan, data) {
  const improved = data.improved_forecast;
  if (!improved) return "";
  const chance = improved.chance_of_goal ?? improved.chance_of_reaching_goal_in_todays_dollars;
  const keys = Object.keys(improved.percentiles ?? {});
  const last = improved.percentiles?.[keys.at(-1)];
  const original = plan.simulation?.chance_of_goal;
  return `<div class="card" style="margin-top:18px">
    <div class="card-head"><h3>Second opinion: the improved forecast</h3>
      ${explainButton("Explain why the improved forecast gives a different chance of reaching my goal than the main simulation.")}</div>
    <p class="muted">Same plan, stricter forecast: whole 12-month stretches of history so crashes stay together, expected
      returns pulled toward what today's bond yields imply, and room for not knowing the true average.</p>
    <div class="grid cols-3" style="margin-top:14px">
      <div class="mini"><span>Chance of the goal (main simulation)</span><b>${percent(original, 0)}</b></div>
      <div class="mini"><span>Chance of the goal (improved forecast)</span><b>${percent(chance, 0)}</b></div>
      <div class="mini"><span>Median outcome (improved)</span><b>${last ? moneyShort(last.p50) : "not known"}</b></div>
    </div>
    <p class="caption">Expected return used: ${percent(improved.expected_annual_return)} a year before inflation.
      Test how accurate this method has been on the <a href="#/analyze">Analyze</a> page.</p>
  </div>`;
}

function planContext(data, plan) {
  const lines = [
    `Inputs: savings ${money(data.inputs.savings)}, ${money(data.inputs.monthly_contribution)} a month, goal ${money(data.inputs.goal)} in today's dollars, ${data.inputs.years} years, tolerated drop ${weight(data.inputs.tolerated_drop)}`,
    `Required real return: ${percent(data.objective?.required_real_return)}`,
  ];
  if (plan) {
    lines.push(`Plan mix: ${mixText(plan.weights)}`);
    lines.push(`Plan expected return ${percent(plan.expected_return)}, volatility ${percent(plan.volatility)}`);
    lines.push(`Chance of reaching the goal: ${percent(plan.simulation?.chance_of_goal, 0)}`);
    lines.push(`Poor outcome ${moneyShort(plan.simulation?.p10_ending_value)}, median ${moneyShort(plan.simulation?.median_ending_value)}, strong ${moneyShort(plan.simulation?.p90_ending_value)}`);
  } else {
    lines.push("No mix meets the rules for these inputs.");
  }
  const contribution = data.contribution_for_80_percent;
  if (contribution != null && typeof contribution !== "object") lines.push(`Monthly contribution for an 80% chance: ${money(contribution)}`);
  const improved = data.improved_forecast;
  if (improved) {
    const chance = improved.chance_of_goal ?? improved.chance_of_reaching_goal_in_todays_dollars;
    lines.push(`Improved forecast chance of the goal: ${percent(chance, 0)}`);
  }
  if (data.stop_condition) lines.push(`Stress test stop condition triggered: ${data.stop_condition.triggered ? "yes" : "no"}`);
  if (data.committee?.outcome) lines.push(`Committee outcome: ${data.committee.outcome}`);
  return lines;
}

function historyHtml(backtest) {
  if (!backtest || !backtest.monthly_values) {
    return `<div class="card"><p class="muted">${escapeHtml(backtest?.message ?? "Not enough history for this test.")}</p></div>`;
  }
  const rows = backtest.summary.map((row) => [
    `<span class="dot" style="background:${PORTFOLIO_COLORS[row.portfolio] ?? "#7A8797"}"></span> ${escapeHtml(row.portfolio)}`,
    money(row.ending_value), money(row.total_contributed), percent(row.worst_peak_to_trough_drop),
    row.portfolio === "Your plan" ? String(row.objective_not_reachable_months) : "—",
  ]);
  return `<div class="card">
      <div class="chart tall" id="personal-history"></div>
      <p class="caption">If you had started this plan ${backtest.years_covered} years ago. Each month the mix was chosen
        using only returns and inflation known at that time. Values are in actual dollars, including your contributions.</p>
    </div>
    <div class="card" style="margin-top:18px">
      ${table([{ label: "Portfolio" }, { label: "Ending value", num: true }, { label: "You put in", num: true },
    { label: "Worst drop", num: true }, { label: "Months the goal return was out of reach", num: true }], rows)}
    </div>
    <div class="card" style="margin-top:18px">
      <h3>How the plan's mix changed over time</h3>
      <div class="chart" id="personal-weights"></div>
      <p class="caption">The mix moves as new data arrives. Large swings here are the same instability the stress test measures.</p>
    </div>`;
}

function todayHtml(data) {
  const tickers = planTickers(data);
  const holdings = data.inputs.holdings;
  const held = Array.isArray(holdings)
    ? Object.fromEntries(tickers.map((fund, index) => [fund, holdings[index] ?? 0])) : (holdings ?? {});
  const fields = tickers.map((fund) => `<label class="field">${fund} you hold now
      <input class="input" data-money data-holding="${fund}" inputmode="numeric" value="${money(held[fund] ?? 0)}"></label>`).join("");
  const trades = data.trades ?? [];
  const tradeRows = trades.map((trade) => {
    const amount = trade.buy_or_sell_dollars;
    const action = Math.abs(amount) < 0.5 ? "Hold" : amount > 0 ? "Buy" : "Sell";
    return [`<strong>${trade.fund}</strong>`, money(trade.target_dollars),
      `<span class="badge ${action === "Buy" ? "approve" : action === "Sell" ? "oppose" : "neutral"}">${action}</span>`,
      money(Math.abs(amount)), money(trade.estimated_cost_dollars, true)];
  });
  const tradeTable = trades.length
    ? table([{ label: "Fund" }, { label: "Target", num: true }, { label: "Action" }, { label: "Amount", num: true },
      { label: "Estimated trading cost", num: true }], tradeRows)
    : `<p class="muted">${escapeHtml(data.trade_message ?? "There is no plan to trade toward yet.")}</p>`;
  return `<div class="card stack">
      <p class="muted">Enter what you hold today to get exact trades. Leave everything at $0 to see how to invest your
        plan money from cash.</p>
      <div class="grid cols-4">${fields}</div>
      <div class="grid cols-4">
        <label class="field">Other cash to invest
          <input class="input" data-money data-other-cash inputmode="numeric" value="${money(data.inputs.other_cash ?? 0)}"></label>
        <div style="display:flex;align-items:flex-end"><button class="button small no-print" type="button" data-update-trades>Update my trades</button></div>
      </div>
    </div>
    <div class="card" style="margin-top:18px">${tradeTable}</div>`;
}

function policyHtml(sections) {
  const body = (sections ?? []).map((section) => (
    `<h3>${escapeHtml(section.title)}</h3><p>${escapeHtml(section.paragraph)}</p>`)).join("");
  return `<div class="document">${body}</div>`;
}

export async function renderPlan(root, navigate) {
  const inputs = cleanInputs(loadInputs());
  const menu = SECTIONS.map(([id, label]) => `<a href="#/personal/plan" data-jump="${id}">${label}</a>`).join("");
  root.innerHTML = `<div class="page">
    <div style="display:flex;flex-wrap:wrap;justify-content:space-between;gap:12px;align-items:baseline">
      <h1 style="font-size:40px">Your plan</h1>
      <a class="no-print" href="#/personal">← Change my answers</a>
    </div>
    <p class="muted" style="margin-top:8px">${money(inputs.savings)} saved · ${money(inputs.monthly_contribution)} a month ·
      goal ${money(inputs.goal)} in today's dollars · ${inputs.years} years · drop limit ${weight(inputs.tolerated_drop)}</p>
    <div id="plan-funds"></div>
    <div id="plan-body" style="margin-top:24px">${skeleton("Building your plan and running 10,000 simulations...", 320)}</div>
  </div>`;
  const body = root.querySelector("#plan-body");

  let data;
  try {
    data = await postPersonalPlan(inputs);
  } catch (error) {
    body.innerHTML = errorCard(error.message);
    return;
  }

  registerFunds(data.universe?.funds ?? []);
  const plan = data.portfolios.find((portfolio) => portfolio.name === "Your plan" && portfolio.weights) ?? null;
  const baselines = data.portfolios.filter((portfolio) => portfolio.name !== "Your plan");
  const dataWindow = data.universe?.window;
  const fundsLine = data.universe && !data.universe.is_default
    ? `<p class="muted" style="margin-top:4px">${data.universe.funds.length} holdings: ${data.universe.funds.map((fund) => escapeHtml(fund.ticker)).join(", ")}
      · data ${dataWindow ? `${escapeHtml(String(dataWindow.first_month).slice(0, 7))} to ${escapeHtml(String(dataWindow.last_month).slice(0, 7))}` : ""}
      · search: ${escapeHtml(data.universe.method ?? "")}</p>` : "";
  root.querySelector("#plan-funds").innerHTML = fundsLine;

  body.innerHTML = `<div class="with-menu">
    <nav class="menu no-print" aria-label="Sections"><div class="menu-title">Your plan</div>${menu}</nav>
    <div>
      <section class="section" id="summary" style="margin-top:0">${summaryHtml(data, plan)}</section>
      <section class="section" id="safety"><h2>First, your safety net</h2>
        <p class="lede">An emergency reserve is set aside before anything is invested, so a surprise bill never forces
          you to sell at a bad time.</p>${safetyHtml(data.emergency_reserve, data.inputs)}</section>
      <section class="section" id="allocation"><h2>Your allocation</h2>
        <p class="lede">The plan, and two simple baselines held to the same rules.</p>${allocationHtml(data, plan, baselines)}
        ${data.screens?.length ? `<h3 style="margin-top:28px">Would Buffett or Burry own these stocks?</h3>
          <p class="muted" style="margin:4px 0 12px">Their checks from the companies' own annual reports (10-K filings),
          using only reports filed by the decision date. Funds have no annual report, so they are not screened.</p>
          ${screensHtml(data.screens)}` : ""}</section>
      <section class="section" id="odds"><h2>Will I make it?</h2>
        <p class="lede">Expected returns are averages. This shows the range of what could actually happen.</p>${oddsHtml(plan, data)}</section>
      <section class="section" id="history"><h2>If you had started years ago</h2>
        <p class="lede">A test with no hindsight: every decision uses only what was known on that day.</p>${historyHtml(data.backtest)}</section>
      <section class="section" id="fragile"><h2>How fragile is this?</h2>
        <p class="lede">Each row changes one thing and asks whether the recommended mix survives.</p>
        ${stopBanner(data.stop_condition, "plan")}
        <div style="margin-top:18px">${stressTables(data.stress ?? [], data.stop_condition)}</div></section>
      <section class="section" id="today"><h2>What do I do today?</h2>
        <p class="lede">Turn the plan into actual trades.</p><div id="today-body">${todayHtml(data)}</div></section>
      <section class="section" id="policy"><h2>Your investment policy statement</h2>
        <p class="lede">Your rules in writing. Foundations and pension funds keep one of these; now you have one too.</p>
        ${policyHtml(data.policy_statement)}</section>
      <section class="section" id="committee"><h2>Committee review</h2>
        <p class="lede">Three investors with different philosophies review the same computed facts.</p>
        <div id="committee-body">${committeeHtml(data.committee)}</div></section>
    </div>
  </div>`;

  setAssistantContext("Personal plan results", planContext(data, plan), [
    "Why is my chance of reaching the goal what it is?",
    "What if I add $200 a month?",
    "What if my goal is $800,000?",
  ], { plan_inputs: data.inputs });

  // Charts
  if (plan) {
    charts.donut(body.querySelector("#personal-donut"), plan.weights, plan.dollars);
    if (data.fan_chart) {
      charts.fan(body.querySelector("#personal-fan"), data.fan_chart,
        { low: "p10", lowMid: "p25", mid: "p50", highMid: "p75", high: "p90" },
        { value: data.inputs.goal, label: `Goal ${moneyShort(data.inputs.goal)}` });
    }
  }
  if (data.backtest?.monthly_values) {
    charts.valueLines(body.querySelector("#personal-history"), data.backtest.monthly_values, { startLabel: "Month" });
    charts.weightAreas(body.querySelector("#personal-weights"), data.backtest.plan_weights);
  }

  // Section menu: jump and highlight
  const links = [...body.querySelectorAll("[data-jump]")];
  links.forEach((link) => link.addEventListener("click", (event) => {
    event.preventDefault();
    body.querySelector(`#${link.dataset.jump}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }));
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      links.forEach((link) => link.classList.toggle("active", link.dataset.jump === entry.target.id));
    }
  }, { rootMargin: "-140px 0px -60% 0px" });
  SECTIONS.forEach(([id]) => { const element = body.querySelector(`#${id}`); if (element) observer.observe(element); });

  // Rebuild buttons
  const rebuild = (changes) => {
    saveInputs({ ...loadInputs(), ...changes });
    renderPlan(root, navigate);
    window.scrollTo({ top: 0 });
  };
  body.querySelector("[data-rebuild-contribution]")?.addEventListener("click", (event) => {
    rebuild({ monthly_contribution: Number(event.currentTarget.dataset.rebuildContribution) });
  });
  body.querySelectorAll("[data-way]").forEach((button) => button.addEventListener("click", () => {
    const next = data.ways_to_make_it_work[Number(button.dataset.way)].new_inputs;
    rebuild({
      savings: next.savings, monthly_contribution: next.monthly_contribution, goal: next.goal, years: next.years,
      tolerated_drop: next.tolerated_drop, monthly_expenses: next.monthly_expenses, reserve_months: next.reserve_months,
    });
  }));

  // Trades
  const wireToday = () => {
    const today = body.querySelector("#today-body");
    today.querySelectorAll("[data-money]").forEach((field) => {
      field.addEventListener("blur", () => { field.value = money(parseMoney(field.value)); });
      field.addEventListener("focus", () => field.select());
    });
    today.querySelector("[data-update-trades]")?.addEventListener("click", async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      const holdings = Object.fromEntries(planTickers(data).map((fund) => [fund, parseMoney(today.querySelector(`[data-holding="${fund}"]`).value)]));
      const otherCash = parseMoney(today.querySelector("[data-other-cash]").value);
      try {
        const updated = await postPersonalPlan({ ...inputs, holdings, other_cash: otherCash });
        today.innerHTML = todayHtml(updated);
        wireToday();
      } catch (error) {
        today.insertAdjacentHTML("beforeend", errorCard(error.message));
        button.disabled = false;
      }
    });
  };
  wireToday();

  // Committee live review
  const committeeBody = body.querySelector("#committee-body");
  const wireCommittee = () => attachLiveReview(committeeBody, { mode: "personal", inputs }, (committee, model) => {
    committeeBody.innerHTML = committeeHtml(committee, model);
    wireCommittee();
  });
  wireCommittee();
}
