// Buffett and Burry checks on individual stocks, from the companies' own 10-K filings (my Lab 18 and 19 rules).
import { escapeHtml } from "./format.js";
import { chip } from "./ui.js";

function scoreBadge(score) {
  if (!score) return `<span class="badge neutral">not applicable</span>`;
  const match = /(\d+)\s*of\s*(\d+)/.exec(String(score));
  const kind = !match ? "neutral" : match[1] === match[2] ? "approve" : match[1] === "0" ? "oppose" : "conditions";
  return `<span class="badge ${kind}">${escapeHtml(score)}</span>`;
}

function checksOf(item, investor) {
  const direct = item[`${investor}_checks`];
  if (Array.isArray(direct)) return direct;
  const all = Array.isArray(item.checks) ? item.checks : [];
  return all.filter((check) => String(check.investor ?? check.group ?? "").toLowerCase().includes(investor));
}

function checkChip(check) {
  const result = check.result === "pass" ? "pass" : check.result === "fail" ? "fail" : "unknown";
  const name = check.label ?? check.name ?? check.check ?? "";
  // The rule's limit is already in its name, so show only what was measured.
  return chip(result, check.measured ? `${name}: ${check.measured}` : name);
}

/** A card per stock with both legends' scores and their checks. */
export function screensHtml(screens) {
  const cards = (screens ?? []).map((item) => {
    const name = item.company_name ?? item.name ?? "";
    const notApplicable = String(item.status ?? "").startsWith("not applicable") || (!item.buffett_score && !item.burry_score);
    if (notApplicable) {
      return `<div class="card stack"><h3>${escapeHtml(item.ticker)}</h3>
        <p class="muted" style="font-size:14px">${escapeHtml(item.status ?? "Not applicable: a fund has no 10-K annual report.")}</p></div>`;
    }
    const buffett = checksOf(item, "buffett");
    const burry = checksOf(item, "burry");
    return `<div class="card stack">
      <div><h3>${escapeHtml(item.ticker)}</h3><p class="muted" style="font-size:13.5px">${escapeHtml(name)}</p></div>
      <div class="kv"><span>Buffett (returns on equity, owner earnings)</span><span>${scoreBadge(item.buffett_score)}</span></div>
      ${buffett.length ? `<div class="chips">${buffett.map(checkChip).join("")}</div>` : ""}
      <div class="kv"><span>Burry (cash backs earnings, debt)</span><span>${scoreBadge(item.burry_score)}</span></div>
      ${burry.length ? `<div class="chips">${burry.map(checkChip).join("")}</div>` : ""}
    </div>`;
  });
  return `<div class="grid cols-3">${cards.join("")}</div>`;
}
