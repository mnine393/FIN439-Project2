// Compass: page router. Routes live in the address bar after "#", so Back and Forward work.
import { openInAnalyze, renderAnalyze } from "./analyze.js";
import { mountAssistant, onAssistantAction, setAssistantContext } from "./assistant.js";
import { redrawAll, resizeAll } from "./charts.js";
import { renderInstitution } from "./institution.js";
import { renderLegend, renderLegendsHome } from "./legends.js";
import { renderHome, renderPlan, saveInputs, loadInputs } from "./personal.js";

const app = document.querySelector("#app");
const MODES = ["personal", "analyze", "institution", "legends"];

function navigate(hash) {
  if (window.location.hash === hash) route();
  else window.location.hash = hash;
}

function setMode(mode) {
  document.querySelectorAll(".mode-switch a").forEach((link) => {
    link.classList.toggle("active", link.dataset.mode === mode);
  });
}

const PAGE_HINTS = {
  personal: ["Personal plan", [
    "Explain the chance of reaching my goal",
    "What is an emergency reserve?",
    "Analyze 60% VT 40% BND on $100,000",
  ]],
  institution: ["Institution (Meridian Foundation endowment)", [
    "Why does the committee vote the way it does?",
    "What is the stop condition?",
    "What is the efficient frontier?",
  ]],
  legends: ["Legends (13F portfolios)", [
    "What does Buffett own?",
    "What does Burry own?",
    "What is a 13F?",
  ]],
};

function route() {
  const parts = window.location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  const mode = MODES.includes(parts[0]) ? parts[0] : "personal";
  setMode(mode);
  window.scrollTo({ top: 0 });
  if (PAGE_HINTS[mode]) setAssistantContext(PAGE_HINTS[mode][0], [], PAGE_HINTS[mode][1]);
  if (mode === "analyze") {
    renderAnalyze(app, navigate, { autorun: parts[1] === "run" });
  } else if (mode === "legends") {
    if (parts[1]) renderLegend(app, parts[1], navigate);
    else renderLegendsHome(app);
  } else if (mode === "institution") {
    renderInstitution(app, parts[1] ?? "summary", navigate);
  } else if (parts[1] === "plan") {
    renderPlan(app, navigate);
  } else {
    renderHome(app, navigate);
  }
}

// ---------- light and dark theme ----------
const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");

function resolvedTheme() {
  const chosen = document.documentElement.dataset.theme;
  if (chosen === "light" || chosen === "dark") return chosen;
  return darkQuery.matches ? "dark" : "light";
}

function applyTheme() {
  document.documentElement.dataset.resolvedTheme = resolvedTheme();
  redrawAll();
}

document.querySelector("#theme-toggle").addEventListener("click", () => {
  const next = resolvedTheme() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try {
    localStorage.setItem("compass.theme", next);
  } catch (error) { /* not remembered; the theme still changes */ }
  applyTheme();
});
darkQuery.addEventListener("change", applyTheme);
applyTheme();

// ---------- Ask Compass ----------
mountAssistant();
onAssistantAction((action) => {
  if (action.action === "analyze" && action.holdings) openInAnalyze(action.holdings, navigate);
  if (action.action === "compare" && action.a) openInAnalyze(action.a, navigate);
  if (action.action === "plan" && action.inputs) {
    const current = loadInputs();
    const { universe, max_single_stock_weight: _a, max_individual_stocks_total: _b, min_holdings: _c, ...rest } = action.inputs;
    saveInputs({ ...current, ...rest, ...(universe ? { universe } : {}) });
    navigate("#/personal/plan");
  }
});

// ---------- first-visit welcome ----------
const WELCOME_KEY = "compass.welcomed.v1";

function showWelcome() {
  const dialog = document.createElement("dialog");
  dialog.className = "welcome";
  dialog.innerHTML = `
    <div class="welcome-top">
      <h2>Welcome to Compass</h2>
      <p>A portfolio planner that shows its work. Every number comes from the model, every forecast is a range, and
        the forecasts are tested against history. Pick where to start:</p>
    </div>
    <div class="welcome-choices">
      <button class="welcome-choice" data-go="#/personal"><span class="icon">🎯</span><b>Plan for a goal</b>
        <span>Tell it what you have, what you add each month, and your goal. Get a mix and your odds.</span></button>
      <button class="welcome-choice" data-go="#/analyze"><span class="icon">🔍</span><b>Analyze a portfolio</b>
        <span>Type in any tickers and amounts. See the risk, crisis replays and where it could go.</span></button>
      <button class="welcome-choice" data-go="#/legends"><span class="icon">🏛️</span><b>Learn from legends</b>
        <span>See what Warren Buffett and Michael Burry actually own, from their SEC filings.</span></button>
    </div>
    <div class="welcome-foot">
      <span>Stuck? Press <b>Ask Compass</b> (bottom right) and ask in plain words. Dotted words show their meaning.</span>
      <button class="button ghost small" data-go="">Just look around</button>
    </div>`;
  document.body.appendChild(dialog);
  dialog.addEventListener("close", () => dialog.remove());
  dialog.querySelectorAll("[data-go]").forEach((button) => button.addEventListener("click", () => {
    try { localStorage.setItem(WELCOME_KEY, "1"); } catch (error) { /* shown again next time */ }
    dialog.close();
    if (button.dataset.go) navigate(button.dataset.go);
  }));
  dialog.showModal();
}

document.querySelector("#help-button").addEventListener("click", showWelcome);
let welcomed = false;
try { welcomed = localStorage.getItem(WELCOME_KEY) === "1"; } catch (error) { welcomed = false; }
if (!welcomed && !window.location.hash) setTimeout(showWelcome, 300);

// Tapping a dotted word on a phone shows its meaning (hover does this on a computer).
document.addEventListener("click", (event) => {
  document.querySelectorAll(".term.show").forEach((element) => element.classList.remove("show"));
  const word = event.target.closest(".term");
  if (word) word.classList.add("show");
});

document.querySelector("#print-button").addEventListener("click", () => {
  if (window.location.hash.startsWith("#/institution")) navigate("#/institution/report");
  else window.print();
});

// Show the two required statements exactly as the service returns them.
fetch("/api/health").then((response) => response.json()).then((body) => {
  const statements = body?.statements;
  if (!Array.isArray(statements) || statements.length < 2) return;
  const band = document.querySelector("#disclosure");
  band.innerHTML = "";
  for (const statement of statements) {
    const span = document.createElement("span");
    span.textContent = statement;
    band.appendChild(span);
  }
  document.querySelector("#footer-statements").textContent = statements.join(" ");
}).catch(() => { /* the built-in text stays */ });

let resizeTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(resizeAll, 150);
});
window.addEventListener("hashchange", route);
route();
