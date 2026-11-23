// The AI Investment Committee section, shared by both modes.
// Rule: the code computes every number and every vote; the artificial intelligence only writes the explanation.
import { postLiveCommittee } from "./api.js";
import { escapeHtml } from "./format.js";
import { chip, errorCard } from "./ui.js";

function voteBadge(vote) {
  const text = String(vote ?? "Cannot judge");
  const lower = text.toLowerCase();
  const kind = lower === "approve" ? "approve" : lower.includes("conditions") ? "conditions"
    : lower.includes("oppose") ? "oppose" : "neutral";
  return `<span class="badge ${kind}">${escapeHtml(text)}</span>`;
}

function sourceLabel(member, modelName) {
  if (member.memo_source === "live") return `Live review by ${escapeHtml(modelName ?? "Claude")}`;
  if (member.memo_source === "saved") return "Saved review written by artificial intelligence from the fact sheet";
  return "Rule-based summary written by code, not by artificial intelligence";
}

/** Highlight any number the code did not compute. */
function memoHtml(member) {
  let html = escapeHtml(member.memo ?? "");
  for (const flagged of member.flagged_numbers ?? []) {
    const safe = escapeHtml(String(flagged)).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    html = html.replace(new RegExp(safe, "g"), (match) => `<mark>${match}</mark>`);
  }
  return html;
}

function checkChip(check) {
  const result = check.result === "pass" ? "pass" : check.result === "fail" ? "fail" : "unknown";
  const detail = [check.measured, check.threshold].filter((part) => part !== null && part !== undefined && part !== "");
  const text = detail.length ? `${check.label}: ${detail.join(" vs ")}` : check.label;
  return chip(result, text);
}

function memberCard(member, modelName) {
  const flagged = member.flagged_numbers ?? [];
  const flagNote = flagged.length
    ? `<div class="banner bad" style="margin-top:12px"><span>✕</span><span>${flagged.length}
        ${flagged.length === 1 ? "number in this memo was" : "numbers in this memo were"} not computed by the code:
        ${flagged.map(escapeHtml).join(", ")}</span></div>`
    : `<p class="caption" style="color:#14724c">✓ Every number in this memo was computed by the code.</p>`;
  return `<div class="card stack">
    <div>
      <h3>${escapeHtml(member.name)}</h3>
      <p class="muted" style="font-size:14px;margin-top:4px">${escapeHtml(member.philosophy ?? "")}</p>
      <div style="margin-top:10px">${voteBadge(member.vote)}</div>
    </div>
    <div class="chips">${(member.checks ?? []).map(checkChip).join("")}</div>
    <div class="memo">${memoHtml(member)}</div>
    ${flagNote}
    <p class="caption">${sourceLabel(member, modelName)}</p>
  </div>`;
}

function tallyChips(tally = {}) {
  const parts = [
    ["approve", "Approve", tally.approve],
    ["conditions", "Approve with conditions", tally.approve_with_conditions],
    ["oppose", "Oppose", tally.oppose],
    ["neutral", "Cannot judge", tally.cannot_judge],
  ].filter(([, , value]) => value);
  return parts.map(([kind, label, value]) => `<span class="badge ${kind}">${value} ${label}</span>`).join(" ");
}

export function committeeHtml(committee, modelName) {
  if (!committee || !committee.members) {
    return `<div class="card"><p class="muted">The committee review is not available from the service yet.</p></div>`;
  }
  return `<div class="stack">
    <div class="card" style="display:flex;flex-wrap:wrap;gap:14px;align-items:center;justify-content:space-between">
      <div><div class="group-title" style="margin:0">Committee outcome</div>
        <div style="font-size:26px;font-weight:800;margin-top:4px">${escapeHtml(committee.outcome ?? "")}</div></div>
      <div class="chips row">${tallyChips(committee.tally)}</div>
      <button class="button small no-print" type="button" data-live-review>Run live review</button>
    </div>
    <div data-live-message></div>
    <div class="grid cols-3">${committee.members.map((member) => memberCard(member, modelName)).join("")}</div>
    <div class="card">
      <p><strong>How this works.</strong> The code computes every number and every vote. The artificial intelligence
      only writes the explanation, and any number it writes that the code did not compute is highlighted in red.</p>
      <details class="more"><summary>What the committee was shown</summary>
        <pre class="raw">${escapeHtml((committee.fact_sheet_lines ?? []).join("\n"))}</pre></details>
    </div>
  </div>`;
}

/**
 * Wire the "Run live review" button. `payload` is what the service needs to rebuild the fact sheet;
 * `rerender` receives the new committee object.
 */
export function attachLiveReview(container, payload, rerender) {
  const button = container.querySelector("[data-live-review]");
  const message = container.querySelector("[data-live-message]");
  if (!button) return;
  button.addEventListener("click", async () => {
    button.disabled = true;
    button.innerHTML = `<span class="spinner"></span>Asking the committee...`;
    message.innerHTML = "";
    try {
      const live = await postLiveCommittee(payload);
      rerender(live.committee ?? live, live.model ?? live.committee?.model);
    } catch (error) {
      message.innerHTML = `<div class="banner info"><span>i</span><span>${escapeHtml(error.message)}
        <span class="detail">The saved review above still works.</span></span></div>`;
      button.disabled = false;
      button.textContent = "Run live review";
    }
  });
}

export { errorCard };
