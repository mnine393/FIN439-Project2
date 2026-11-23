// Small building blocks shared by both modes. Each returns an HTML string.
import {
  PORTFOLIO_COLORS, escapeHtml, fundColor, fundWhat, mixText, money, percent, points, tickersOf, verdictSentence,
  weight,
} from "./format.js";

export function metricCard({ label, value, note = "", tone = "", extra = "", medium = false }) {
  return `<div class="card metric ${tone}">
    <div class="label">${escapeHtml(label)}</div>
    <div class="value ${medium ? "medium" : ""}">${escapeHtml(value)}</div>
    ${note ? `<div class="note">${note}</div>` : ""}
    ${extra}
  </div>`;
}

export function chip(result, text) {
  const kind = result === "pass" ? "pass" : result === "fail" ? "fail" : "unknown";
  const mark = kind === "pass" ? "✓" : kind === "fail" ? "✕" : "?";
  return `<span class="chip ${kind}"><span class="mark">${mark}</span><span>${escapeHtml(text)}</span></span>`;
}

export function verdictChips(verdicts) {
  if (!verdicts || !verdicts.length) return "";
  const chips = verdicts.map((verdict) => chip(verdict.pass ? "pass" : "fail", verdictSentence(verdict)));
  return `<div class="chips">${chips.join("")}</div>`;
}

export function weightBar(weights) {
  if (!weights) return `<span class="muted">No mix</span>`;
  const parts = tickersOf(weights).filter((fund) => weights[fund] > 0.0001).map((fund) => (
    `<i style="width:${weights[fund] * 100}%;background:${fundColor(fund)}" title="${fund} ${weight(weights[fund])}"></i>`));
  return `<div class="weightbar" role="img" aria-label="${escapeHtml(mixText(weights))}">${parts.join("")}</div>`;
}

export function fundLegend(weights, dollars) {
  return tickersOf(weights).map((fund) => {
    const what = fundWhat(fund);
    return `<div class="legend-line">
      <span class="dot" style="background:${fundColor(fund)}"></span>
      <span><b>${fund} ${weight(weights[fund])}</b>${dollars ? ` · ${money(dollars[fund])}` : ""}
      ${what ? `<span class="muted"> · ${escapeHtml(what)}</span>` : ""}</span>
    </div>`;
  }).join("");
}

export function portfolioCard(portfolio, { title, rows = [] } = {}) {
  const name = title ?? portfolio.name;
  const color = PORTFOLIO_COLORS[portfolio.name] ?? "#7A8797";
  const facts = [
    ["Mix", mixText(portfolio.weights)],
    ["Expected return", `${percent(portfolio.expected_return)} a year`],
    ["Volatility", percent(portfolio.volatility)],
    ...rows,
  ].map(([key, value]) => `<div class="kv"><span>${escapeHtml(key)}</span><span>${escapeHtml(value)}</span></div>`);
  return `<div class="card portfolio-card stack">
    <h3><span class="dot" style="background:${color}"></span>${escapeHtml(name)}</h3>
    ${weightBar(portfolio.weights)}
    <div>${facts.join("")}</div>
    ${verdictChips(portfolio.verdicts)}
  </div>`;
}

export function stopBanner(stop, subject = "plan") {
  if (!stop) return "";
  if (!stop.triggered) {
    return `<div class="banner good"><span>✓</span><span>Stable: no stress case moves the mix by more than
      ${points(stop.threshold)}.</span></div>`;
  }
  if (String(stop.reason ?? "").startsWith("no mix")) {
    return `<div class="banner bad"><span>✕</span><span>Stop: no mix meets the rules in the base case.
      <span class="detail">There is no ${subject} to stress until one of the inputs changes.</span></span></div>`;
  }
  const cases = stop.triggered_case_count;
  const noMix = stop.no_mix_case_count ?? 0;
  const moved = stop.largest_weight_change && stop.largest_weight_change_case
    ? ` The largest move is ${points(stop.largest_weight_change)} (${escapeHtml(stop.largest_weight_change_case)}).` : "";
  const noMixText = noMix ? ` In ${noMix} of them no mix meets the rules at all.` : "";
  return `<div class="banner bad"><span>✕</span><span>Stop condition triggered: this ${subject} is not stable.
    <span class="detail">${cases} stress ${cases === 1 ? "case moves" : "cases move"} a fund's weight by more than
    ${points(stop.threshold)} or leave no mix at all.${moved}${noMixText}</span></span></div>`;
}

const STRESS_GROUPS = ["Estimates", "Data window", "Costs", "Rules"];

export function stressTables(rows, stop) {
  const triggered = new Set(stop?.triggered_cases ?? []);
  const sections = STRESS_GROUPS.map((group) => {
    const groupRows = rows.filter((row) => row.group === group);
    if (!groupRows.length) return "";
    const body = groupRows.map((row) => {
      const noMix = !row.weights;
      const isTrigger = triggered.has(row.case) || noMix;
      const cost = row.trading_cost_dollars != null ? ` · cost ${money(row.trading_cost_dollars)}` : "";
      const afterCost = row.expected_return_after_cost != null && group === "Costs"
        ? ` · return after cost ${percent(row.expected_return_after_cost)}` : "";
      return `<tr class="${isTrigger ? "trigger" : ""}">
        <td>${escapeHtml(row.case)}<div class="muted" style="font-size:12.5px">${escapeHtml(cost + afterCost).replace(/^ · /, "")}</div></td>
        <td>${weightBar(row.weights)}<div class="muted" style="font-size:12.5px;margin-top:4px">${escapeHtml(mixText(row.weights))}</div></td>
        <td>${chip(row.meets_objective ? "pass" : "fail", row.meets_objective ? "Meets the objective" : noMix ? "No mix meets the rules" : "Misses the objective")}</td>
        <td class="num">${noMix ? "no mix" : points(row.largest_weight_change)}</td>
      </tr>`;
    }).join("");
    return `<div class="card">
      <p class="group-title">${group}</p>
      <div class="table-wrap"><table class="data">
        <thead><tr><th>What changed</th><th>Resulting mix</th><th>Result</th><th class="num">Largest weight change</th></tr></thead>
        <tbody>${body}</tbody>
      </table></div>
    </div>`;
  });
  return `<div class="stack">${sections.join("")}</div>`;
}

/** A tiny safe Markdown renderer: headings, bullets, block quotes, links, bold. HTML is escaped first. */
export function markdown(text) {
  const inline = (line) => escapeHtml(line)
    .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
  const out = [];
  let list = false;
  const closeList = () => { if (list) { out.push("</ul>"); list = false; } };
  let tableRows = [];
  const closeTable = () => {
    if (!tableRows.length) return;
    const cells = (row) => row.replace(/^\||\|$/g, "").split("|").map((cell) => inline(cell.trim()));
    const [head, ...body] = tableRows.filter((row) => !/^\|?\s*:?-{2,}/.test(row));
    out.push(`<div class="table-wrap"><table class="data"><thead><tr>${cells(head).map((cell) => `<th>${cell}</th>`).join("")}</tr></thead>
      <tbody>${body.map((row) => `<tr>${cells(row).map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
    tableRows = [];
  };
  for (const raw of String(text ?? "").split(/\r?\n/)) {
    const line = raw.trimEnd();
    if (line.trim().startsWith("|")) { closeList(); tableRows.push(line.trim()); continue; }
    closeTable();
    if (!line.trim()) { closeList(); continue; }
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (heading) { closeList(); const level = Math.min(heading[1].length + 1, 4); out.push(`<h${level}>${inline(heading[2])}</h${level}>`); continue; }
    const bullet = /^\s*[-*]\s+(.*)$/.exec(line);
    if (bullet) { if (!list) { out.push("<ul>"); list = true; } out.push(`<li>${inline(bullet[1])}</li>`); continue; }
    const quote = /^>\s?(.*)$/.exec(line);
    if (quote) { closeList(); out.push(`<blockquote>${inline(quote[1])}</blockquote>`); continue; }
    closeList();
    out.push(`<p>${inline(line)}</p>`);
  }
  closeList();
  closeTable();
  return `<div class="prose">${out.join("")}</div>`;
}

export function skeleton(message, height = 160) {
  return `<div class="skeleton" style="min-height:${height}px">${escapeHtml(message)}</div>`;
}

export function errorCard(message) {
  return `<div class="card error-card"><strong>Something went wrong.</strong>
    <p style="margin-top:6px">${escapeHtml(message)}</p></div>`;
}

export function table(headers, rows) {
  const head = headers.map((header) => `<th class="${header.num ? "num" : ""}">${escapeHtml(header.label)}</th>`).join("");
  const body = rows.map((row) => `<tr>${row.map((cell, index) => (
    `<td class="${headers[index].num ? "num" : ""}">${cell}</td>`)).join("")}</tr>`).join("");
  return `<div class="table-wrap"><table class="data"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}
