// Every chart on the site. Plotly is loaded once from /vendor/plotly.min.js (no network needed).
import { PORTFOLIO_COLORS, fundColor, fundWhat, mixText, money, moneyShort, percent, tickersOf, weight } from "./format.js";

const FONT = { family: '-apple-system, "Segoe UI", Inter, Roboto, Arial, sans-serif', color: "#0B1F3A", size: 13 };
const CONFIG = { displayModeBar: false, responsive: true };
const GRID = "#E4E8EE";

function baseLayout(extra = {}) {
  return {
    font: FONT,
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    margin: { l: 64, r: 20, t: 16, b: 48 },
    hoverlabel: { bgcolor: "#0B1F3A", font: { color: "#fff", family: FONT.family } },
    legend: { orientation: "h", y: -0.2, x: 0 },
    xaxis: { showgrid: false, zeroline: false, linecolor: GRID, ticks: "outside", tickcolor: GRID },
    yaxis: { gridcolor: GRID, zeroline: false },
    ...extra,
  };
}

function cssVar(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

/** Swap the light-theme ink and grid colors for the current theme's colors (dark mode support). */
function themed(object) {
  const ink = cssVar("--chart-ink", "#0B1F3A");
  const grid = cssVar("--chart-grid", GRID);
  return JSON.parse(JSON.stringify(object)
    .replace(/#0B1F3A/gi, ink)
    .replace(new RegExp(GRID, "gi"), grid));
}

const drawn = new Map();

function draw(element, traces, layout) {
  if (!element || !window.Plotly) return;
  drawn.set(element, { traces, layout });
  const dark = document.documentElement.dataset.resolvedTheme === "dark";
  const finalLayout = themed(layout);
  if (dark) finalLayout.hoverlabel = { bgcolor: "#e8eef7", font: { color: "#0b1220", family: FONT.family } };
  window.Plotly.react(element, traces.map((trace) => (trace.marker?.line?.color === "#fff" && dark
    ? { ...trace, marker: { ...trace.marker, line: { ...trace.marker.line, color: cssVar("--card", "#fff") } } }
    : trace)), finalLayout, CONFIG);
}

/** Redraw every chart after the theme changes. */
export function redrawAll() {
  for (const [element, { traces, layout }] of drawn) {
    if (element.isConnected) draw(element, traces, layout);
    else drawn.delete(element);
  }
}

// ---------- charts for the Analyze page ----------

/** Horizontal bars: rows [{label, value, color?, text?}], values are fractions shown as percents. */
export function bars(element, rows, { title = "", group = null } = {}) {
  const traces = group
    ? group.map((series) => ({
      type: "bar", orientation: "h", name: series.name, y: rows.map((row) => row.label),
      x: rows.map((row) => (series.values[row.label] ?? 0) * 100), marker: { color: series.color },
      hovertemplate: `${series.name} %{y}: %{x:.1f}%<extra></extra>`,
    }))
    : [{
      type: "bar", orientation: "h", y: rows.map((row) => row.label), x: rows.map((row) => row.value * 100),
      marker: { color: rows.map((row) => row.color ?? "#00A37A") },
      text: rows.map((row) => row.text ?? `${(row.value * 100).toFixed(1)}%`), textposition: "outside", cliponaxis: false,
      hovertemplate: "%{y}: %{x:.1f}%<extra></extra>",
    }];
  draw(element, traces, baseLayout({
    barmode: "group",
    margin: { l: 150, r: 48, t: 10, b: 44 },
    xaxis: { title: { text: title }, ticksuffix: "%", gridcolor: GRID, zeroline: true, zerolinecolor: GRID },
    yaxis: { automargin: true, autorange: "reversed", showgrid: false },
    showlegend: Boolean(group),
  }));
}

/** Correlation heat map: tickers, matrix (numbers from -1 to 1). */
export function heatmap(element, tickers, matrix) {
  draw(element, [{
    type: "heatmap", x: tickers, y: tickers, z: matrix, zmin: -1, zmax: 1,
    colorscale: [[0, "#2563EB"], [0.5, "#F3F5F8"], [1, "#D64545"]],
    text: matrix.map((row) => row.map((value) => value.toFixed(2))), texttemplate: "%{text}",
    hovertemplate: "%{y} and %{x}: %{z:.2f}<extra></extra>", colorbar: { thickness: 12, outlinewidth: 0 },
  }], baseLayout({
    margin: { l: 64, r: 20, t: 10, b: 64 },
    xaxis: { showgrid: false, side: "bottom" }, yaxis: { showgrid: false, autorange: "reversed" },
  }));
}

/** Growth of $10,000 (line) with the drawdown below it (area), sharing one time axis. */
export function growthAndDrawdown(element, growth, drawdown) {
  const months = growth.map((row) => row.month);
  draw(element, [
    { x: months, y: growth.map((row) => row.value), mode: "lines", name: "Growth of $10,000",
      line: { color: "#00A37A", width: 2.5 }, hovertemplate: "%{x|%b %Y}: $%{y:,.0f}<extra></extra>" },
    { x: drawdown.map((row) => row.month), y: drawdown.map((row) => row.drawdown * 100), yaxis: "y2", mode: "lines",
      name: "Drop from the last high", fill: "tozeroy", line: { color: "#D64545", width: 1 }, fillcolor: "rgba(214,69,69,0.25)",
      hovertemplate: "%{x|%b %Y}: %{y:.1f}% below the last high<extra></extra>" },
  ], baseLayout({
    grid: { rows: 2, columns: 1, roworder: "top to bottom" },
    xaxis: { showgrid: false, linecolor: GRID },
    yaxis: { domain: [0.38, 1], title: { text: "Value ($)" }, tickprefix: "$", gridcolor: GRID },
    yaxis2: { domain: [0, 0.28], title: { text: "Drop (%)" }, ticksuffix: "%", gridcolor: GRID, rangemode: "tozero" },
    hovermode: "x unified",
  }));
}

/** Crisis replays: one bar per scenario, red for losses. */
export function scenarioBars(element, scenarios) {
  draw(element, [{
    type: "bar", x: scenarios.map((row) => row.name), y: scenarios.map((row) => row.portfolio_return * 100),
    marker: { color: scenarios.map((row) => (row.portfolio_return < 0 ? "#D64545" : "#1E9E6A")) },
    text: scenarios.map((row) => `${(row.portfolio_return * 100).toFixed(1)}%`), textposition: "outside", cliponaxis: false,
    hovertemplate: "%{x}: %{y:.1f}%<extra></extra>",
  }], baseLayout({
    margin: { l: 56, r: 20, t: 24, b: 64 },
    yaxis: { title: { text: "Portfolio return (%)" }, ticksuffix: "%", gridcolor: GRID, zeroline: true, zerolinecolor: GRID },
    xaxis: { showgrid: false },
    showlegend: false,
  }));
}

/** Walk-forward forecast check: the 10th-90th band each forecast gave, and what really happened. */
export function calibrationChart(element, outcomes, label) {
  const dates = outcomes.map((row) => row[0]);
  const inside = outcomes.filter((row) => row[4] >= row[1] && row[4] <= row[3]);
  const outside = outcomes.filter((row) => row[4] < row[1] || row[4] > row[3]);
  const pct = (value) => (value - 1) * 100;
  draw(element, [
    { x: dates, y: outcomes.map((row) => pct(row[1])), mode: "lines", line: { width: 0 }, showlegend: false, hoverinfo: "skip" },
    { x: dates, y: outcomes.map((row) => pct(row[3])), mode: "lines", line: { width: 0 }, fill: "tonexty",
      fillcolor: "rgba(0,163,122,0.18)", name: "Forecast range (10th to 90th percentile)", hoverinfo: "skip" },
    { x: dates, y: outcomes.map((row) => pct(row[2])), mode: "lines", line: { color: "#00A37A", width: 1.5, dash: "dot" },
      name: "Forecast median", hovertemplate: "Forecast made %{x|%b %Y}: median %{y:.1f}%<extra></extra>" },
    { x: inside.map((row) => row[0]), y: inside.map((row) => pct(row[4])), mode: "markers", name: "Actual (inside the range)",
      marker: { color: "#0B1F3A", size: 5 }, hovertemplate: "Actual %{y:.1f}%<extra></extra>" },
    { x: outside.map((row) => row[0]), y: outside.map((row) => pct(row[4])), mode: "markers", name: "Actual (outside the range)",
      marker: { color: "#D64545", size: 6 }, hovertemplate: "Actual %{y:.1f}% (outside)<extra></extra>" },
  ], baseLayout({
    xaxis: { title: { text: "Date the forecast was made" }, showgrid: false, linecolor: GRID },
    yaxis: { title: { text: `${label} return (%)` }, ticksuffix: "%", gridcolor: GRID, zeroline: true, zerolinecolor: GRID },
    hovermode: "closest",
  }));
}

/** Two forecast fans on one chart (improved method filled, simple method as dashed lines). */
export function fanCompare(element, improved, simple, contributed) {
  const years = improved.map((row) => row.month / 12);
  const top = Math.max(...improved.map((row) => row.p90), ...simple.map((row) => row.p90));
  const axis = dollarAxis(top, "Value");
  const scaled = (rows, key) => rows.map((row) => row[key] / axis.scale);
  const traces = [
    { x: years, y: scaled(improved, "p10"), mode: "lines", line: { width: 0 }, showlegend: false, hoverinfo: "skip" },
    { x: years, y: scaled(improved, "p90"), mode: "lines", line: { width: 0 }, fill: "tonexty", fillcolor: "rgba(0,163,122,0.15)",
      name: "Improved: 10th to 90th percentile", hoverinfo: "skip" },
    { x: years, y: scaled(improved, "p25"), mode: "lines", line: { width: 0 }, showlegend: false, hoverinfo: "skip" },
    { x: years, y: scaled(improved, "p75"), mode: "lines", line: { width: 0 }, fill: "tonexty", fillcolor: "rgba(0,163,122,0.3)",
      name: "Improved: middle half", hoverinfo: "skip" },
    { x: years, y: scaled(improved, "p50"), mode: "lines", line: { color: "#00A37A", width: 3 }, name: "Improved: median",
      text: improved.map((row) => `Improved median: ${moneyShort(row.p50)}`), hoverinfo: "text+x" },
    { x: years, y: scaled(simple, "p50"), mode: "lines", line: { color: "#7A8797", width: 2, dash: "dash" }, name: "Simple: median",
      text: simple.map((row) => `Simple median: ${moneyShort(row.p50)}`), hoverinfo: "text+x" },
    { x: years, y: scaled(simple, "p10"), mode: "lines", line: { color: "#7A8797", width: 1, dash: "dot" }, name: "Simple: 10th and 90th",
      text: simple.map((row) => `Simple 10th percentile: ${moneyShort(row.p10)}`), hoverinfo: "text+x" },
    { x: years, y: scaled(simple, "p90"), mode: "lines", line: { color: "#7A8797", width: 1, dash: "dot" }, showlegend: false,
      text: simple.map((row) => `Simple 90th percentile: ${moneyShort(row.p90)}`), hoverinfo: "text+x" },
  ];
  const shapes = contributed ? [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: contributed / axis.scale, y1: contributed / axis.scale,
    line: { color: "#0B1F3A", width: 1.2, dash: "dash" } }] : [];
  const annotations = contributed ? [{ xref: "paper", x: 0.01, y: contributed / axis.scale, yanchor: "bottom", xanchor: "left",
    text: "Money put in", showarrow: false, font: { size: 12, color: "#0B1F3A" } }] : [];
  draw(element, traces, baseLayout({
    xaxis: { title: { text: "Years from today" }, showgrid: false, linecolor: GRID },
    yaxis: { title: axis.title, gridcolor: GRID, rangemode: "tozero", tickprefix: "$", ticksuffix: axis.suffix },
    shapes, annotations, hovermode: "x unified",
  }));
}

/** Pick dollar units from the data so axes read "$1.2M" or "$400K". */
function dollarAxis(maxValue, title) {
  if (maxValue >= 1e6) return { title: { text: `${title} ($ millions)` }, scale: 1e6, suffix: "M" };
  return { title: { text: `${title} ($ thousands)` }, scale: 1e3, suffix: "K" };
}

export function donut(element, weights, dollars) {
  const funds = tickersOf(weights).filter((fund) => weights[fund] > 0.0001);
  draw(element, [{
    type: "pie",
    hole: 0.62,
    labels: funds,
    values: funds.map((fund) => weights[fund]),
    marker: { colors: funds.map((fund) => fundColor(fund)), line: { color: "#fff", width: 3 } },
    text: funds.map((fund) => `${fund}<br>${weight(weights[fund])}`),
    textinfo: "text",
    textposition: "outside",
    hovertext: funds.map((fund) => `${fund}${fundWhat(fund) ? ` (${fundWhat(fund)})` : ""}: ${weight(weights[fund])}${dollars ? `, ${money(dollars[fund])}` : ""}`),
    hoverinfo: "text",
    sort: false,
    direction: "clockwise",
  }], baseLayout({ showlegend: false, margin: { l: 24, r: 24, t: 24, b: 24 } }));
}

/**
 * Fan chart of simulated values over time.
 * rows: [{month, ...}], keys: {low, lowMid, mid, highMid, high}, line: {value, label}.
 */
export function fan(element, rows, keys, line, color = "#00A37A") {
  const years = rows.map((row) => row.month / 12);
  const top = Math.max(...rows.map((row) => row[keys.high]), line?.value ?? 0);
  const axis = dollarAxis(top, "Value");
  const scaled = (key) => rows.map((row) => row[key] / axis.scale);
  const hover = (label, key) => rows.map((row) => `${label}: ${moneyShort(row[key])} after ${(row.month / 12).toFixed(1)} years`);
  const band = (key, fillColor, name) => ({
    x: years, y: scaled(key), mode: "lines", line: { width: 0 }, fill: "tonexty", fillcolor: fillColor, name, hoverinfo: "skip",
  });
  const traces = [
    { x: years, y: scaled(keys.low), mode: "lines", line: { width: 0 }, showlegend: false, hoverinfo: "skip" },
    band(keys.high, `${color}22`, "Most outcomes (outer band)"),
    { x: years, y: scaled(keys.lowMid), mode: "lines", line: { width: 0 }, showlegend: false, hoverinfo: "skip" },
    band(keys.highMid, `${color}44`, "Middle half of outcomes"),
    { x: years, y: scaled(keys.mid), mode: "lines", line: { color, width: 3 }, name: "Median outcome", text: hover("Median", keys.mid), hoverinfo: "text" },
    { x: years, y: scaled(keys.low), mode: "lines", line: { color, width: 1, dash: "dot" }, name: "Poor outcome", text: hover("Poor outcome", keys.low), hoverinfo: "text" },
    { x: years, y: scaled(keys.high), mode: "lines", line: { color, width: 1, dash: "dot" }, name: "Strong outcome", text: hover("Strong outcome", keys.high), hoverinfo: "text" },
  ];
  const shapes = [];
  const annotations = [];
  if (line) {
    shapes.push({ type: "line", xref: "paper", x0: 0, x1: 1, y0: line.value / axis.scale, y1: line.value / axis.scale, line: { color: "#0B1F3A", width: 1.5, dash: "dash" } });
    annotations.push({ xref: "paper", x: 0.01, y: line.value / axis.scale, yanchor: "bottom", xanchor: "left", text: line.label, showarrow: false, font: { size: 12, color: "#0B1F3A" } });
  }
  draw(element, traces, baseLayout({
    xaxis: { title: { text: "Years from today" }, showgrid: false, zeroline: false, linecolor: GRID },
    yaxis: { title: axis.title, gridcolor: GRID, rangemode: "tozero", tickprefix: "$", ticksuffix: axis.suffix, zeroline: false },
    shapes, annotations, hovermode: "closest",
  }));
}

/** Dollar value over time for several portfolios. series: {name: [{month, value}]} */
export function valueLines(element, series, { startLabel } = {}) {
  const names = Object.keys(series);
  const top = Math.max(...names.flatMap((name) => series[name].map((row) => row.value)));
  const axis = dollarAxis(top, "Value");
  const traces = names.map((name) => ({
    x: series[name].map((row) => String(row.month).slice(0, 10)),
    y: series[name].map((row) => row.value / axis.scale),
    mode: "lines",
    name,
    line: { color: PORTFOLIO_COLORS[name] ?? "#7A8797", width: name.includes("plan") || name.includes("Constrained") ? 3 : 2 },
    text: series[name].map((row) => `${name}: ${moneyShort(row.value)}`),
    hoverinfo: "text+x",
  }));
  draw(element, traces, baseLayout({
    xaxis: { title: { text: startLabel ?? "Month" }, showgrid: false, linecolor: GRID },
    yaxis: { title: axis.title, gridcolor: GRID, tickprefix: "$", ticksuffix: axis.suffix, zeroline: false },
    hovermode: "x unified",
  }));
}

/** Stacked area of the plan's weights over time. rows: [{month, SGOV, IEF, USIG, VT}] */
export function weightAreas(element, rows) {
  const skip = new Set(["month", "value", "net_return", "turnover", "objective_not_reachable"]);
  const funds = tickersOf(Object.fromEntries(Object.keys(rows[0] ?? {}).filter((key) => !skip.has(key)).map((key) => [key, 1])));
  const traces = funds.map((fund) => ({
    x: rows.map((row) => String(row.month).slice(0, 10)),
    y: rows.map((row) => (row[fund] ?? 0) * 100),
    stackgroup: "weights",
    mode: "lines",
    name: fundWhat(fund) ? `${fund} (${fundWhat(fund)})` : fund,
    line: { width: 0.5, color: fundColor(fund) },
    fillcolor: fundColor(fund),
    hovertemplate: `${fund}: %{y:.0f}%<extra></extra>`,
  }));
  draw(element, traces, baseLayout({
    xaxis: { title: { text: "Month" }, showgrid: false, linecolor: GRID },
    yaxis: { title: { text: "Share of the portfolio (%)" }, range: [0, 100], ticksuffix: "%", gridcolor: GRID },
    hovermode: "x unified",
  }));
}

/** Risk and return of every mix, with the mandate-compliant ones and the three portfolios highlighted. */
export function frontier(element, mixes, portfolios, objective) {
  const split = (keep) => mixes.filter((mix) => Boolean(mix.meets_mandate) === keep);
  const cloud = (rows, color, size, name, opacity) => ({
    x: rows.map((mix) => mix.volatility * 100),
    y: rows.map((mix) => mix.expected_return * 100),
    mode: "markers",
    type: "scattergl",
    name,
    marker: { color, size, opacity },
    text: rows.map((mix) => `${mix.weights && typeof Object.values(mix.weights)[0] === "number" ? `${mixText(mix.weights)}<br>` : ""}Return ${percent(mix.expected_return)} · Risk ${percent(mix.volatility)}`),
    hoverinfo: "text",
  });
  const traces = [
    cloud(split(false), "#B8C2CE", 5, "Mixes that break a rule or miss the objective", 0.45),
    cloud(split(true), "#00A37A", 9, "Mixes that meet every rule", 0.95),
  ];
  for (const portfolio of portfolios) {
    if (!portfolio.weights) continue;
    traces.push({
      x: [portfolio.volatility * 100],
      y: [portfolio.expected_return * 100],
      mode: "markers+text",
      name: portfolio.name,
      text: [portfolio.name],
      textposition: "top center",
      textfont: { size: 12, color: "#0B1F3A" },
      marker: { color: PORTFOLIO_COLORS[portfolio.name] ?? "#0B1F3A", size: 16, line: { color: "#fff", width: 2 }, symbol: "diamond" },
      hovertext: [`${portfolio.name}<br>${mixText(portfolio.weights)}<br>Return ${percent(portfolio.expected_return)} · Risk ${percent(portfolio.volatility)}`],
      hoverinfo: "text",
    });
  }
  const shapes = [];
  const annotations = [];
  if (objective != null) {
    shapes.push({ type: "line", xref: "paper", x0: 0, x1: 1, y0: objective * 100, y1: objective * 100, line: { color: "#0B1F3A", width: 1.5, dash: "dash" } });
    annotations.push({ xref: "paper", x: 0.01, y: objective * 100, yanchor: "bottom", xanchor: "left", text: `Objective ${percent(objective)}`, showarrow: false, font: { size: 12 } });
  }
  draw(element, traces, baseLayout({
    xaxis: { title: { text: "Risk: yearly volatility (%)" }, ticksuffix: "%", showgrid: false, linecolor: GRID, rangemode: "tozero" },
    yaxis: { title: { text: "Expected return per year (%)" }, ticksuffix: "%", gridcolor: GRID },
    shapes, annotations, hovermode: "closest",
  }));
}

export function resizeAll() {
  if (!window.Plotly) return;
  document.querySelectorAll(".js-plotly-plot").forEach((element) => window.Plotly.Plots.resize(element));
}
