// Ask Compass: the AI chat panel on every page. The AI answers by running the Compass engine;
// every number it writes is checked against what the engine printed, and unchecked numbers are flagged.
import { escapeHtml } from "./format.js";
import { markdown } from "./ui.js";

const state = {
  open: false,
  busy: false,
  sessionId: null,
  available: null,
  statusMessage: "",
  messages: [],      // {role: "user"|"assistant"|"error", text, steps, actions, unverified}
  page: "home",
  contextLines: [],
  pageData: {},      // structured facts the built-in mode needs (plan inputs, holdings)
  mode: null,        // "ai" with a key, "built-in" without one
  suggestions: [],
  onAction: null,
};

const TOOL_LABELS = {
  build_personal_plan: "Built a personal plan",
  analyze_portfolio: "Analyzed a portfolio",
  compare_portfolios: "Compared two portfolios",
  forecast_calibration: "Tested past forecast accuracy",
  look_up_ticker: "Looked up a ticker",
  legend_holdings: "Read a 13F filing",
  stock_screen: "Ran a stock screen",
};

const DEFAULT_SUGGESTIONS = [
  "Analyze 60% VT 40% BND on $100,000",
  "What does Buffett own?",
  "What is a Sharpe ratio?",
];

/** Pages call this so the AI knows what the user is looking at. Lines are short "label: value" text. */
export function setAssistantContext(page, lines = [], suggestions = [], data = {}) {
  state.page = page;
  state.pageData = data;
  state.contextLines = lines.filter(Boolean).slice(0, 80);
  state.suggestions = suggestions.length ? suggestions : DEFAULT_SUGGESTIONS;
  if (state.open) renderPanel();
}

/** Called with an action from the AI (for example "open this portfolio in Analyze"). */
export function onAssistantAction(handler) {
  state.onAction = handler;
}

/** Open the panel and ask a question right away (used by the "Explain this" buttons). */
export function askCompass(question) {
  openPanel();
  send(question);
}

/** A small "Explain this" button for any card. */
export function explainButton(question, label = "Explain this") {
  return `<button class="explain-button no-print" type="button" data-ask="${escapeHtml(question)}">
    <svg viewBox="0 0 20 20" width="14" height="14" aria-hidden="true"><path d="M10 2l1.8 4.6L16.5 8l-4.7 1.4L10 14l-1.8-4.6L3.5 8l4.7-1.4z" fill="currentColor"/></svg>
    ${escapeHtml(label)}</button>`;
}

function openPanel() {
  state.open = true;
  document.body.classList.add("chat-open");
  renderPanel();
  if (state.available === null) checkStatus();
  setTimeout(() => document.querySelector("#chat-input")?.focus(), 50);
}

function closePanel() {
  state.open = false;
  document.body.classList.remove("chat-open");
  renderPanel();
}

async function checkStatus() {
  try {
    const response = await fetch("/api/assistant/status");
    const body = await response.json();
    state.available = Boolean(body.available);
    state.mode = body.mode ?? (body.available ? "ai" : "built-in");
    state.statusMessage = body.message ?? "";
  } catch (error) {
    state.available = false;
    state.statusMessage = "The Compass service is not reachable.";
  }
  renderPanel();
}

async function send(text) {
  const message = String(text ?? "").trim();
  if (!message || state.busy) return;
  state.messages.push({ role: "user", text: message });
  state.busy = true;
  renderPanel();
  try {
    const response = await fetch("/api/assistant/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message, session_id: state.sessionId, page: state.page, context_lines: state.contextLines,
        page_data: state.pageData,
      }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body?.detail ?? `The assistant failed (${response.status}).`);
    state.sessionId = body.session_id;
    state.messages.push({
      role: "assistant", text: body.reply, steps: body.steps ?? [], actions: body.actions ?? [],
      unverified: body.unverified_numbers ?? [],
    });
  } catch (error) {
    state.messages.push({ role: "error", text: error.message });
  } finally {
    state.busy = false;
    renderPanel();
  }
}

function actionButtons(actions) {
  return actions.map((action, index) => {
    const label = action.action === "analyze" ? "Open this portfolio in Analyze"
      : action.action === "compare" ? "Open this comparison"
      : action.action === "plan" ? "Open this plan" : null;
    return label ? `<button class="button ghost small" data-action-index="${index}" type="button">${label}</button>` : "";
  }).join("");
}

function messageHtml(message, index) {
  if (message.role === "user") return `<div class="bubble user">${escapeHtml(message.text)}</div>`;
  if (message.role === "error") return `<div class="bubble error">${escapeHtml(message.text)}</div>`;
  const steps = (message.steps ?? []).map((step) => (
    `<span class="step-pill ${step.ok ? "" : "failed"}">${step.ok ? "✓" : "✕"} ${escapeHtml(TOOL_LABELS[step.tool] ?? step.tool)}</span>`)).join("");
  const verified = message.unverified?.length
    ? `<div class="verify warn">⚠ Not verified against the engine: ${message.unverified.map(escapeHtml).join(", ")}</div>`
    : `<div class="verify ok">✓ Every number checked against the Compass engine</div>`;
  return `<div class="bubble assistant" data-message="${index}">
    ${steps ? `<div class="steps-row">${steps}</div>` : ""}
    ${markdown(message.text)}
    ${verified}
    ${message.actions?.length ? `<div class="action-row">${actionButtons(message.actions)}</div>` : ""}
  </div>`;
}

function renderPanel() {
  let panel = document.querySelector("#chat-panel");
  if (!panel) return;
  panel.hidden = !state.open;
  document.querySelector("#chat-launcher").setAttribute("aria-expanded", String(state.open));
  if (!state.open) return;
  const offNotice = state.mode === "built-in" && !state.messages.length
    ? `<div class="chat-off"><strong>Built-in mode (free).</strong> Answers come from fixed rules that run the
       Compass engine, so it understands the kinds of questions shown below rather than anything at all.
       <div class="muted" style="margin-top:6px">Adding an Anthropic API key turns on the full AI assistant.</div></div>` : "";
  const intro = !state.messages.length
    ? `<div class="chat-intro">
        <p><strong>Ask about your portfolio or plan.</strong> Answers come from running the Compass engine, and
        every number is checked against it.</p>
        <div class="suggestions">${state.suggestions.map((text) => (
          `<button type="button" class="suggestion" data-suggest="${escapeHtml(text)}">${escapeHtml(text)}</button>`)).join("")}</div>
      </div>` : "";
  const thinking = state.busy ? `<div class="bubble assistant thinking"><span class="dots"><i></i><i></i><i></i></span> Running the engine…</div>` : "";
  panel.innerHTML = `
    <div class="chat-head">
      <div><strong>Ask Compass</strong><span class="chat-model">${state.mode === "ai" ? "Claude · runs the Compass engine" : state.mode === "built-in" ? "Built-in mode · free · runs the Compass engine" : "Assistant"}</span></div>
      <div class="chat-head-actions">
        <button class="icon-button" type="button" id="chat-new" title="New conversation" aria-label="New conversation">↺</button>
        <button class="icon-button" type="button" id="chat-close" title="Close" aria-label="Close">✕</button>
      </div>
    </div>
    <div class="chat-body" id="chat-body">${offNotice}${intro}${state.messages.map(messageHtml).join("")}${thinking}</div>
    <form class="chat-form" id="chat-form">
      <textarea id="chat-input" class="input" rows="1" placeholder="Ask about this page, or describe a portfolio…" ${state.busy ? "disabled" : ""}></textarea>
      <button class="button" type="submit" ${state.busy ? "disabled" : ""} aria-label="Send">↑</button>
    </form>
    <div class="chat-foot">Education, not investment advice. AI answers can be wrong; numbers are checked.</div>`;
  const body = panel.querySelector("#chat-body");
  body.scrollTop = body.scrollHeight;
  panel.querySelector("#chat-close").addEventListener("click", closePanel);
  panel.querySelector("#chat-new").addEventListener("click", () => {
    state.messages = [];
    state.sessionId = null;
    renderPanel();
  });
  const input = panel.querySelector("#chat-input");
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      panel.querySelector("#chat-form").requestSubmit();
    }
  });
  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 140)}px`;
  });
  panel.querySelector("#chat-form").addEventListener("submit", (event) => {
    event.preventDefault();
    send(input.value);
  });
  panel.querySelectorAll("[data-suggest]").forEach((button) => {
    button.addEventListener("click", () => send(button.dataset.suggest));
  });
  panel.querySelectorAll("[data-action-index]").forEach((button) => {
    button.addEventListener("click", () => {
      const message = state.messages[Number(button.closest("[data-message]").dataset.message)];
      const action = message.actions[Number(button.dataset.actionIndex)];
      if (state.onAction) state.onAction(action);
    });
  });
}

export function mountAssistant() {
  const launcher = document.createElement("button");
  launcher.id = "chat-launcher";
  launcher.className = "chat-launcher no-print";
  launcher.type = "button";
  launcher.setAttribute("aria-controls", "chat-panel");
  launcher.innerHTML = `<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
    <path d="M12 2l2.2 5.6L20 9.5l-5.8 1.7L12 17l-2.2-5.8L4 9.5l5.8-1.9z" fill="currentColor"/>
    <path d="M19 15l1 2.4 2.4 1-2.4 1L19 22l-1-2.6-2.4-1 2.4-1z" fill="currentColor" opacity=".7"/></svg>
    <span>Ask Compass</span>`;
  launcher.addEventListener("click", () => (state.open ? closePanel() : openPanel()));
  const panel = document.createElement("aside");
  panel.id = "chat-panel";
  panel.className = "chat-panel no-print";
  panel.setAttribute("aria-label", "Ask Compass assistant");
  panel.hidden = true;
  document.body.append(launcher, panel);
  // Any "Explain this" button anywhere on the site opens the chat with its question.
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-ask]");
    if (button) askCompass(button.dataset.ask);
  });
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      state.open ? closePanel() : openPanel();
    }
    if (event.key === "Escape" && state.open) closePanel();
  });
  state.suggestions = DEFAULT_SUGGESTIONS;
}
