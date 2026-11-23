"""Ask Compass, built-in mode: answers common questions with no AI service and no cost.

When no Anthropic key is set, the chat still works. Instead of a language model, plain rules recognize the
question (a what-if about a plan, a portfolio to analyze, a term to define, a chart to explain) and run
the same Compass engine tools the AI would use. Every number in the answer comes from those tools, and
the same number check runs afterwards.

It understands a fixed set of question types, listed in HELP_TEXT. Anything else gets that list back.
"""
from __future__ import annotations

import re

GLOSSARY = {
    "volatility": "Volatility is how much the value swings from year to year. A volatility of 10% means a "
                  "typical year lands within about 10 percentage points of the average year.",
    "sharpe": "The Sharpe ratio is the return earned above cash for each unit of volatility taken. Higher is "
              "better; above 0.5 is decent for a whole portfolio.",
    "sortino": "The Sortino ratio is like the Sharpe ratio but counts only downside swings as risk.",
    "beta": "Beta is how much the portfolio moves when global stocks move. 1.0 moves with the market; 0.5 "
            "moves about half as much.",
    "drawdown": "A drawdown is the fall from a high point to a later low point. The largest drawdown is the "
                "worst such fall in the history tested.",
    "percentile": "The 10th percentile is a poor outcome: only 1 in 10 simulated futures did worse. The 90th "
                  "percentile is a strong outcome: only 1 in 10 did better. The median is the middle.",
    "median": "The median is the middle outcome: half of the simulated futures did better and half did worse.",
    "correlation": "Correlation measures whether two holdings move together (near 1), independently (near 0), "
                   "or in opposite directions (below 0). Low correlation is what makes diversification work.",
    "expense ratio": "An expense ratio is the yearly fee a fund takes from its value. 0.10% costs $10 a year "
                     "on $10,000.",
    "calibration": "A forecast is well calibrated when its ranges are honest: an 80% range should contain "
                   "about 80% of what really happens. Compass tests this on its own past forecasts.",
    "diversification": "Diversification means owning holdings that do not all fall at the same time, so the "
                       "whole portfolio swings less than its parts.",
    "risk score": "The risk score is a 1-to-10 summary of how bumpy the ride is, based on volatility: 1 is "
                  "like cash and 10 is like a single volatile stock.",
    "emergency reserve": "The emergency reserve is cash set aside for surprise bills before anything is "
                         "invested, so a bad month never forces you to sell in a downturn.",
    "real return": "A real return is the return after inflation, so it measures what the money can buy.",
    "stop condition": "The stop condition is a safety check: if small changes to the inputs flip the "
                      "recommended mix, the plan is not stable enough to trust as is.",
    "13f": "A 13F is the report large investment managers file with the SEC every quarter, listing the U.S. "
           "stocks they own. It is a snapshot up to 45 days old and leaves out cash, bonds and short positions.",
    "bootstrap": "A bootstrap simulation builds possible futures by drawing real months (or, in the improved "
                 "method, whole 12-month stretches) from history at random.",
    "efficient frontier": "The efficient frontier is the set of mixes that give the most expected return for "
                          "each level of risk.",
    "expected return": "The expected return is the average yearly return the model expects. Real years will be "
                       "higher or lower; the forecast range shows how much.",
}

EXPLANATIONS = {
    "forecast": ("The forecast simulates 10,000 possible futures. The improved method draws whole 12-month "
                 "stretches of real history so crashes stay together, pulls expected returns halfway toward "
                 "what today's bond yields imply instead of assuming the last 18 years repeat, and allows for not "
                 "knowing the true average. The shaded band holds 80% of the futures; the line is the median."),
    "calibration": ("The accuracy test goes back to every month in the past, makes the forecast Compass would "
                    "have made then using only data known then, and checks what really happened. An honest "
                    "80% range should catch about 80% of real outcomes. Lower error scores are better."),
    "risk": ("A holding's share of risk counts both how much it swings and how it moves with everything else. "
             "Stocks usually carry far more of a portfolio's risk than their share of the money."),
    "crisis": ("The crisis replays apply this exact mix to the real monthly returns of the 2008 financial crisis, "
               "the 2020 COVID crash and the 2022 rate shock. A holding that did not exist yet is estimated "
               "from how it moves with the market, and is labeled as estimated."),
    "chance": ("The chance of reaching the goal is the share of 10,000 simulated futures, in today's dollars, that "
               "end at or above the goal. It depends on the gap between the return the goal needs and the return "
               "the mix can expect within your drop limit."),
    "fragile": ("The stress test changes one input at a time (estimates, data window, costs, rules) and checks "
                "whether the recommended mix moves by more than the stop threshold. If it does, the plan is "
                "fragile: the answer depends heavily on assumptions nobody knows for sure."),
    "committee": ("Three members with different philosophies vote using checks computed by code: the Endowment "
                  "Builder wants growth, the Indexer wants low cost and simplicity, and the Risk Skeptic wants "
                  "protection from large drops. The vote comes from those checks, not from opinion."),
}

HELP_TEXT = """I am the built-in assistant (no AI service is connected, so there is no cost). I can:
- **Re-run your plan with a change**: "What if I add $200 a month?", "What if my goal is $800,000?", "What if I have 25 years?"
- **Analyze a portfolio**: "Analyze 50000 VTI, 30000 VXUS, 20000 BND" (or use percents and an amount)
- On the Analyze page: "Make this safer", "Which holding adds the most risk?", "How did it do in 2008?"
- **Legends**: "What does Buffett own?", "What does Burry own?"
- **Define a term**: "What is a Sharpe ratio?", "What is volatility?"
- **Explain** any chart with its "Explain this" button.

For open-ended questions, an Anthropic API key turns on the full AI assistant."""

SAFER_RULE = ("A simple safer version keeps 70% of each holding and moves 30% into bonds and cash "
              "(20% IEF government bonds, 10% SGOV Treasury bills).")

# Fixed wording whose numbers are part of the rules, not results; the number check accepts them.
FIXED_TEXTS = [SAFER_RULE]

MONEY = r"\$?\s*(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|m|million)?"


def _amount(text: str, suffix: str | None) -> float:
    value = float(text.replace(",", ""))
    scale = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6}.get((suffix or "").lower(), 1)
    return value * scale


def _pct(value) -> str:
    return "not known" if value is None else f"{value * 100:.1f}%"


def _money(value) -> str:
    if value is None:
        return "not known"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.1f} million"
    return f"${value:,.0f}"


# ---------- reading the question ----------

def plan_changes(question: str, inputs: dict) -> tuple[dict, list[str]] | None:
    """Turn 'what if I add $200 a month' style questions into changed plan inputs."""
    text = question.lower()
    changed = dict(inputs)
    notes = []
    monthly = re.search(r"(add|increase|put in|save|contribute|invest)(?: an extra| another| more)?\s*" + MONEY
                        + r"\s*(?:more\s*)?(?:a|per|each|every)\s*month", text)
    if monthly:
        amount = _amount(monthly.group(2), monthly.group(3))
        extra = monthly.group(1) in ("add", "increase") or re.search(r"extra|another|more", monthly.group(0))
        changed["monthly_contribution"] = inputs["monthly_contribution"] + amount if extra else amount
        notes.append(f"monthly contribution {_money(inputs['monthly_contribution'])} to "
                     f"{_money(changed['monthly_contribution'])}")
    goal = re.search(r"goal (?:is|of|was|were|to)?\s*" + MONEY, text)
    if goal:
        changed["goal"] = _amount(goal.group(1), goal.group(2))
        notes.append(f"goal {_money(inputs['goal'])} to {_money(changed['goal'])}")
    years = re.search(r"(\d{1,2})\s*(?:more\s*)?years", text)
    if years:
        value = int(years.group(1))
        changed["years"] = inputs["years"] + value if re.search(r"\d+\s*more\s*years|extra|another", text) else value
        notes.append(f"years {inputs['years']} to {changed['years']}")
    drop = re.search(r"(?:drop|loss|fall)(?: limit| of)?\s*(?:of|to)?\s*(\d{1,2})\s*%", text)
    if drop:
        changed["tolerated_drop"] = int(drop.group(1)) / 100
        notes.append(f"tolerated drop {inputs['tolerated_drop'] * 100:.0f}% to {drop.group(1)}%")
    saved = re.search(r"(?:savings (?:of|is|to|were|was)|i saved|start with|have saved)\s*" + MONEY
                      + r"(?!\s*(?:a|per)\s*month)", text)
    if saved and not monthly and not goal:
        changed["savings"] = _amount(saved.group(1), saved.group(2))
        notes.append(f"savings {_money(inputs['savings'])} to {_money(changed['savings'])}")
    return (changed, notes) if notes else None


SKIP_WORDS = {"A", "I", "IN", "OF", "AND", "THE", "ON", "MY", "ME", "WITH", "FOR", "TO", "IS", "AT", "ANALYZE",
              "YEARS", "YEAR", "MONTH", "PER", "OR", "AN", "IT", "THIS", "MAKE", "WHAT", "IF", "INTO", "PUT",
              "ADD", "SAVE", "GOAL", "HAVE", "WITH", "ABOUT", "OVER", "AFTER", "BY", "EXTRA", "MORE", "IS", "WAS"}
TICKER = r"([A-Z][A-Z.\-]{0,6})"
NUMBER = r"(\d[\d,]*(?:\.\d+)?)"


def holdings_from_text(question: str) -> dict | None:
    """Read 'VTI 50000, BND 20000', '50k AAPL' or '60% VT 40% BND on $250,000' as dollar holdings."""
    text = question.upper().replace("$", "")
    # Percent mixes first: "60% VT" (percent before the ticker) or "VT 60%" (after).
    percents = re.findall(NUMBER + r"\s*%\s*(?:IN|OF)?\s*" + TICKER + r"\b", text)
    percents = [(ticker, number) for number, ticker in percents] or re.findall(r"\b" + TICKER + r"\s*[:=]?\s*" + NUMBER + r"\s*%", text)
    percents = [(ticker, number) for ticker, number in percents if ticker not in SKIP_WORDS]
    if percents:
        total_match = re.search(r"(?:ON|OF|WITH|FOR|INVEST|TOTAL)\s*" + NUMBER + r"\s*(K|THOUSAND|M|MILLION)?\b(?!\s*%)", text)
        total = _amount(total_match.group(1), total_match.group(2)) if total_match else 100_000
        return {ticker: float(number.replace(",", "")) / 100 * total for ticker, number in percents}
    # Dollar amounts: "VTI 50000" or "50k VTI".
    pairs = re.findall(r"\b" + TICKER + r"\s*[:=]?\s*" + NUMBER + r"\s*(K|THOUSAND)?\b", text)
    pairs += [(ticker, number, suffix) for number, suffix, ticker in
              re.findall(NUMBER + r"\s*(K|THOUSAND)?\s*(?:IN|OF)?\s+" + TICKER + r"\b", text)]
    holdings: dict[str, float] = {}
    for ticker, number, suffix in pairs:
        if ticker in SKIP_WORDS or ticker in holdings:
            continue
        holdings[ticker] = _amount(number, suffix)
    holdings = {ticker: value for ticker, value in holdings.items() if value > 0}
    return holdings or None


# ---------- answers ----------

def _plan_answer(run_tool, inputs: dict, changed: dict, notes: list[str]) -> tuple[str, list]:
    before_text, _ = run_tool("build_personal_plan", inputs)
    after_text, extra = run_tool("build_personal_plan", changed)

    def chance(text):
        match = re.search(r"Your plan: .*?chance of reaching the goal ([\d.]+%|not known)", text)
        return match.group(1) if match else "no plan meets the rules"

    def needed(text):
        match = re.search(r"Monthly contribution for an 80% chance: (\$[\d,.]+(?: million)?)", text)
        return match.group(1) if match else "not known"

    def mix(text):
        match = re.search(r"Your plan: mix ([^;]+);", text)
        return match.group(1) if match else "no mix meets the rules"

    reply = (f"I re-ran your plan with {', '.join(notes)}.\n\n"
             f"- **Chance of reaching the goal:** {chance(before_text)} before, **{chance(after_text)}** after\n"
             f"- **Mix:** {mix(before_text)} before, {mix(after_text)} after\n"
             f"- **Monthly contribution for an 80% chance:** {needed(before_text)} before, {needed(after_text)} after\n\n"
             "Use the button below to open the changed plan.")
    return reply, [extra]


def _analysis_summary(payload: dict, holdings: dict) -> str:
    history = payload["history"]
    improved = payload["forecast"]["improved"]
    last = list(improved["percentiles"])[-1]
    band = improved["percentiles"][last]
    years = int(last) // 12
    contributions = payload.get("risk_contribution", {})
    total_share = sum(contributions.values()) or 1
    top = max(contributions, key=contributions.get) if contributions else None
    crises = [row for row in payload.get("crisis_scenarios", []) if row.get("portfolio_return") is not None]
    worst = min(crises, key=lambda row: row["portfolio_return"]) if crises else None
    lines = [
        f"**{', '.join(f'{ticker} {_money(value)}' for ticker, value in holdings.items())}**",
        f"- **Risk score:** {payload['risk_score']['score']} of 10 (volatility {_pct(history['volatility'])} a year)",
        f"- **History:** {_pct(history['annual_return'])} a year; largest drop {_pct(history['maximum_drawdown'])}",
        f"- **Improved forecast after {years} years:** median {_money(band['p50'])}, 80% range "
        f"{_money(band['p10'])} to {_money(band['p90'])}; expected return {_pct(improved['expected_annual_return'])} a year",
    ]
    if top:
        lines.append(f"- **Most of the risk:** {top} carries {_pct(contributions[top] / total_share)} of it")
    if worst:
        lines.append(f"- **Worst crisis replay:** {worst['name']}, {_pct(worst['portfolio_return'])}")
    for flag in payload.get("flags", []):
        lines.append(f"- Flag: {flag}")
    return "\n".join(lines)


def _analyze(run_tool, holdings: dict) -> tuple[dict, dict]:
    text, extra = run_tool("analyze_portfolio", {"holdings": holdings})
    return extra, text


def answer(question: str, page: str | None, page_data: dict, run_tool, call_engine) -> tuple[str, list[dict]]:
    """Return (reply in Markdown, actions for the website). run_tool runs a named engine tool."""
    text = question.lower().strip()
    page_name = (page or "").lower()
    plan_inputs = page_data.get("plan_inputs")
    page_holdings = page_data.get("holdings")

    # 1. What-if questions about the personal plan.
    if plan_inputs and re.search(r"what if|if i|add|increase|goal|years|drop|contribute|save", text):
        parsed = plan_changes(question, plan_inputs)
        if parsed:
            return _plan_answer(run_tool, plan_inputs, *parsed)

    # 2. A portfolio typed into the question.
    typed = holdings_from_text(question) if re.search(r"\d", text) else None
    if typed and (len(typed) >= 2 or re.search(r"analy[sz]e|portfolio", text)):
        payload = call_engine("/api/analyze", {"holdings": typed})
        return (_analysis_summary(payload, typed) + "\n\nOpen it on the Analyze page for the charts.",
                [{"action": "analyze", "holdings": typed}])

    # 3. Questions about the portfolio on the Analyze page.
    if page_holdings and re.search(r"safer|less risk|lower risk|conservative|defensive", text):
        total = sum(page_holdings.values())
        safer = {ticker: value * 0.7 for ticker, value in page_holdings.items()}
        safer["IEF"] = safer.get("IEF", 0) + total * 0.2
        safer["SGOV"] = safer.get("SGOV", 0) + total * 0.1
        payload = call_engine("/api/compare", {"a": page_holdings, "b": safer})
        a, b = payload["details"]["a"], payload["details"]["b"]
        last_a = list(a["forecast"]["improved"]["percentiles"])[-1]
        last_b = list(b["forecast"]["improved"]["percentiles"])[-1]
        reply = (SAFER_RULE + "\n\n"
                 f"| | Yours | Safer |\n|---|---|---|\n"
                 f"| Risk score | {a['risk_score']['score']} of 10 | {b['risk_score']['score']} of 10 |\n"
                 f"| Volatility | {_pct(a['history']['volatility'])} | {_pct(b['history']['volatility'])} |\n"
                 f"| Largest drop | {_pct(a['history']['maximum_drawdown'])} | {_pct(b['history']['maximum_drawdown'])} |\n"
                 f"| Expected return | {_pct(a['forecast']['improved']['expected_annual_return'])} | "
                 f"{_pct(b['forecast']['improved']['expected_annual_return'])} |\n"
                 f"| Poor case (10th percentile) | {_money(a['forecast']['improved']['percentiles'][last_a]['p10'])} | "
                 f"{_money(b['forecast']['improved']['percentiles'][last_b]['p10'])} |\n"
                 f"| Median | {_money(a['forecast']['improved']['percentiles'][last_a]['p50'])} | "
                 f"{_money(b['forecast']['improved']['percentiles'][last_b]['p50'])} |\n\n"
                 "Safer usually means a better poor case and a lower median: you give up some upside for a "
                 "smaller worst case.")
        return reply, [{"action": "analyze", "holdings": safer}]
    if page_holdings and re.search(r"most risk|riskiest|risk come|share of risk|risk contribution|risk score|diversif|2008|crisis|covid|2022", text):
        payload = call_engine("/api/analyze", {"holdings": page_holdings})
        summary = _analysis_summary(payload, page_holdings)
        topic = "crisis" if re.search(r"2008|crisis|covid|2022", text) else "risk"
        extra = ""
        if re.search(r"diversif", text):
            concentration = payload["concentration"]
            extra = (f"\n\nWith {concentration['number_of_holdings']} holdings, it behaves like "
                     f"{concentration['effective_number_of_holdings']:.1f} equal-sized ones. "
                     + GLOSSARY["diversification"])
        return EXPLANATIONS[topic] + "\n\n" + summary + extra, []

    # 4. Legends.
    for key, person in (("buffett", "Warren Buffett"), ("burry", "Michael Burry")):
        if key in text and re.search(r"own|hold|portfolio|13f|buy|strategy|stocks", text):
            payload = call_engine(f"/api/legends/{key}", None)
            holdings = [row for row in payload.get("holdings", []) if row.get("ticker")][:10]
            summary = payload.get("summary", {})
            lines = [f"**{person}'s latest 13F** (report for {summary.get('report_period', 'not known')}, "
                     f"filed {summary.get('filing_date', 'not known')}): the top 10 stock holdings."]
            lines += [f"- {row['ticker']} ({row.get('issuer', '').title()}): {_pct(row.get('weight'))}" for row in holdings]
            lines.append("\n" + GLOSSARY["13f"])
            top10 = sum(row.get("weight", 0) for row in holdings) or 1
            return "\n".join(lines), [{"action": "analyze", "holdings": {
                row["ticker"]: round(row.get("weight", 0) / top10 * 100_000) for row in holdings}}]

    # 5. Definitions.
    for word, meaning in GLOSSARY.items():
        if word in text and re.search(r"what|mean|define|explain|is a|is the", text):
            return meaning, []

    # 6. Explain buttons and general "why" questions use the page's own numbers.
    for topic, keywords in (("calibration", r"accura|calibrat"), ("forecast", r"forecast|range|where it could go"),
                            ("crisis", r"crisis|2008|replay"), ("risk", r"risk contribution|share of risk|risk come"),
                            ("chance", r"chance|odds|make it|reach"), ("fragile", r"fragile|stop condition|stress"),
                            ("committee", r"committee|oppose|approve|vote")):
        if re.search(keywords, text):
            context = page_data.get("context_lines", [])
            relevant = [line for line in context if re.search(keywords + r"|chance|return|mix|outcome", line.lower())][:6]
            numbers = ("\n\nOn this page:\n" + "\n".join(f"- {line}" for line in relevant)) if relevant else ""
            return EXPLANATIONS[topic] + numbers, []

    return HELP_TEXT, []
