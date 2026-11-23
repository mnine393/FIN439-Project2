"""Code-computed fact sheets, committee checks, and optional live reviews."""
from __future__ import annotations

import os
import re
from pathlib import Path


ENDOWMENT_MINIMUM_STOCK_WEIGHT = 0.50
ENDOWMENT_MINIMUM_CHANCE = 0.50
ENDOWMENT_MINIMUM_HORIZON_YEARS = 7
INDEXER_MAXIMUM_TURNOVER = 0.02
RISK_MAXIMUM_INSTITUTION_FLOOR_CHANCE = 0.33
RISK_MINIMUM_PERSONAL_GOAL_FRACTION = 0.50
MEMO_DIRECTORY = Path("memos")
MEMBER_NAMES = ("Endowment Builder", "Indexer", "Risk Skeptic")


def _plan(payload: dict, mode: str) -> dict | None:
    """Return the selected plan record, if the response has one."""
    name = "Constrained portfolio" if mode == "institution" else "Your plan"
    return next((row for row in payload.get("portfolios", []) if row.get("name") == name), None)


def _backtest_row(payload: dict, name: str) -> dict | None:
    """Find one named point-in-time backtest result."""
    backtest = payload.get("backtest", {})
    for rows in (backtest.get("table", []), backtest.get("summary", [])):
        if hasattr(rows, "to_dict"):
            rows = rows.to_dict("records")
        row = next((item for item in rows if item.get("portfolio") == name), None)
        if row is not None:
            return row
    return None


def _money(value: float | None) -> str:
    """Format a dollar value without inventing a new calculation."""
    return "not known" if value is None else f"${value:,.0f}"


def _percent(value: float | None) -> str:
    """Format a fractional measure as a percentage."""
    return "not known" if value is None else f"{value:.2%}"


def _line(label: str, value: str) -> str:
    """Make one fact-sheet line."""
    return f"{label}: {value}"


def _screen_passes(screen: dict, investor: str) -> bool | None:
    """Tell whether a reduced stock screen passed every check for one investor."""
    score = screen.get(f"{investor}_score")
    if not isinstance(score, str) or " of " not in score:
        return None
    passed, total = score.split(" of ", 1)
    try:
        return int(passed) == int(total)
    except ValueError:
        return None


def _add_individual_stock_facts(facts: dict, lines: list[str], payload: dict, universe: list[dict]) -> None:
    """Add disclosed stock quality evidence when a plan includes individual stocks."""
    tickers = [fund["ticker"] for fund in universe if fund.get("role") == "individual stock"]
    if not tickers:
        facts["has_individual_stocks"] = False
        return
    by_ticker = {screen.get("ticker"): screen for screen in payload.get("screens", [])}
    screens = [by_ticker.get(ticker) for ticker in tickers]
    facts["has_individual_stocks"] = True
    facts["individual_stock_screens"] = screens
    for investor, label in (("buffett", "Buffett"), ("burry", "Burry")):
        results = [_screen_passes(screen, investor) if screen is not None else None for screen in screens]
        facts[f"{investor}_stock_results"] = results
        count = sum(result is True for result in results)
        lines.append(_line(f"Individual stocks passing all of {label}'s checks", f"{count} of {len(tickers)}"))
    for ticker, screen in zip(tickers, screens):
        if screen is None:
            lines.append(_line(f"Individual stock {ticker} scores", "not known"))
        else:
            lines.append(_line(f"Individual stock {ticker} scores",
                               f"Buffett {screen.get('buffett_score', 'not known')}; Burry {screen.get('burry_score', 'not known')}"))


def build_fact_sheet(mode: str, payload: dict) -> tuple[dict, list[str]]:
    """Extract the finished response's facts and their printed presentation."""
    if mode not in ("institution", "personal"):
        raise ValueError("Committee mode must be institution or personal.")
    plan = _plan(payload, mode)
    has_mix = bool(plan and plan.get("weights"))
    cpi = payload.get("cpi_signal", {})
    if mode == "personal":
        cpi = {**payload.get("objective", {}), **cpi}
    inflation = cpi.get("inflation")
    inflation_month = cpi.get("month") if mode == "institution" else None
    facts = {
        "mode": mode,
        "has_mix": has_mix,
        "who": payload.get("mandate", {}).get("name") if mode == "institution" else "Personal savings plan",
        "objective": (payload.get("mandate", {}).get("objective_spread") if mode == "institution"
                      else payload.get("objective", {}).get("required_return")),
        "inflation": inflation,
        "inflation_month": inflation_month,
        "horizon_years": (payload.get("mandate", {}).get("horizon_years") if mode == "institution"
                          else payload.get("inputs", {}).get("years")),
        "weights": plan.get("weights") if has_mix else None,
        "expected_return": plan.get("expected_return") if has_mix else None,
        "volatility": plan.get("volatility") if has_mix else None,
        "worst_12_month_return": plan.get("worst_12_month_return") if has_mix else None,
        "chance": (plan.get("simulation", {}).get("probability_objective")
                   if mode == "institution" and has_mix
                   else plan.get("simulation", {}).get("chance_of_goal") if has_mix else None),
        "stop": payload.get("stop_condition", {}),
    }
    universe = payload.get("universe", {}).get("funds", [])
    stock_tickers = [fund["ticker"] for fund in universe
                     if fund.get("role") in ("stocks", "individual stock")]
    if payload.get("universe", {}).get("is_default"):
        facts["stock_weight"] = None if facts["weights"] is None else facts["weights"].get("VT")
        facts["stock_label"] = "Stocks (VT)"
    else:
        facts["stock_weight"] = None if facts["weights"] is None else sum(
            facts["weights"].get(ticker, 0.0) for ticker in stock_tickers)
        facts["stock_label"] = "Stocks"
    plan_name = "the plan" if mode == "personal" else "the constrained portfolio"
    lines = [_line("Plan for", facts["who"] or "not known")]
    objective_label = ("Objective (return needed)" if mode == "personal"
                       else "Objective (return above inflation)")
    lines.append(_line(objective_label, _percent(facts["objective"])))
    inflation_text = _percent(inflation)
    if inflation_month:
        inflation_text = f"{inflation_text} ({inflation_month})"
    lines.append(_line("Inflation", inflation_text))
    if mode == "personal":
        goal = payload.get("inputs", {}).get("goal")
        lines.append(_line("Goal", _money(goal)))
        half_goal = None if goal is None else goal * RISK_MINIMUM_PERSONAL_GOAL_FRACTION
        lines.append(_line("Half of the goal", _money(half_goal)))
    horizon = facts["horizon_years"]
    lines.append(_line("Horizon", "not known" if horizon is None else f"{horizon} years"))
    _add_individual_stock_facts(facts, lines, payload, universe)
    if not payload.get("universe", {}).get("is_default"):
        lines.append(_line("Total stocks", _percent(facts["stock_weight"])))
    if not has_mix:
        lines.append("Plan mix: no mix meets the mandate")
        lines.extend([
            "Expected return: not known",
            "Volatility: not known",
            "Worst 12-month return: not known",
            "Chance of meeting the objective or goal: not known",
            "Plan-dependent backtest and stress facts: not known",
        ])
        return facts, lines
    for fund, weight in facts["weights"].items():
        lines.append(_line(f"Plan weight {fund}", _percent(weight)))
    lines.extend([
        _line("Expected return", _percent(facts["expected_return"])),
        _line("Volatility", _percent(facts["volatility"])),
        _line("Worst 12-month return", _percent(facts["worst_12_month_return"])),
        _line("Chance of meeting the objective" if mode == "institution" else "Chance of meeting the goal",
              _percent(facts["chance"])),
    ])
    if mode == "institution":
        simulation = plan.get("simulation", {})
        facts["floor_chance"] = simulation.get("probability_below_90m")
        facts["median_ending_value"] = simulation.get("median_ending_value")
        lines.extend([
            _line("Chance of falling below $90 million", _percent(facts["floor_chance"])),
            _line("Median ending value", _money(facts["median_ending_value"])),
        ])
    else:
        simulation = plan.get("simulation", {})
        facts["p10_ending_value"] = simulation.get("p10_ending_value")
        facts["median_ending_value"] = simulation.get("median_ending_value")
        facts["p90_ending_value"] = simulation.get("p90_ending_value")
        facts["contribution_for_80_percent"] = payload.get("contribution_for_80_percent")
        lines.extend([
            _line("10th percentile ending value", _money(facts["p10_ending_value"])),
            _line("Median ending value", _money(facts["median_ending_value"])),
            _line("90th percentile ending value", _money(facts["p90_ending_value"])),
            _line("Monthly contribution for an 80% chance", _money(facts["contribution_for_80_percent"])),
        ])
    _add_backtest_facts(facts, lines, payload, mode, plan_name)
    _add_stress_facts(facts, lines, payload, mode)
    return facts, lines


def _add_backtest_facts(facts: dict, lines: list[str], payload: dict, mode: str, plan_name: str) -> None:
    """Add comparable backtest facts to a fact sheet."""
    plan_row = _backtest_row(payload, "Constrained portfolio" if mode == "institution" else "Your plan")
    benchmark = _backtest_row(payload, "60/40 benchmark")
    equal = _backtest_row(payload, "Equal weight")
    facts["backtest_plan"] = plan_row
    facts["backtest_benchmark"] = benchmark
    facts["backtest_equal_weight"] = equal
    for label, row in ((plan_name, plan_row), ("the 60/40 benchmark", benchmark), ("equal weight", equal)):
        if row is None:
            lines.append(_line(f"Point-in-time backtest ending value for {label}", "not known"))
            lines.append(_line(f"Worst backtest drop for {label}", "not known"))
        else:
            ending = row.get("ending_dollar_value", row.get("ending_value"))
            lines.append(_line(f"Point-in-time backtest ending value for {label}", _money(ending)))
            worst_drop = _percent(row.get("worst_peak_to_trough_drop"))
            lines.append(_line(f"Worst backtest drop for {label}", worst_drop))
    facts["unreachable_months"] = None if plan_row is None else plan_row.get("objective_not_reachable_months")
    facts["average_turnover"] = None if plan_row is None else plan_row.get("average_turnover")
    facts["total_contributed"] = None if plan_row is None else plan_row.get("total_contributed")
    unreachable = facts["unreachable_months"]
    unreachable_text = "not known" if unreachable is None else str(unreachable)
    lines.append(_line("Months the objective was not reachable", unreachable_text))
    lines.append(_line("Average monthly turnover", _percent(facts["average_turnover"])))
    if mode == "personal":
        lines.append(_line("Total contributed in the backtest", _money(facts["total_contributed"])))


def _add_stress_facts(facts: dict, lines: list[str], payload: dict, mode: str) -> None:
    """Add stop and sensitivity facts without recalculating the stress cases."""
    stop = facts["stop"]
    triggered = stop.get("triggered")
    facts["vt_lower_mix_meets"] = next((row.get("meets_objective") for row in payload.get("stress", [])
                                         if row.get("case") == "VT expected return one point lower"), None)
    stop_text = "not known" if triggered is None else ("triggered" if triggered else "stable")
    cases = stop.get("triggered_case_count")
    change = stop.get("largest_weight_change")
    case = stop.get("largest_weight_change_case")
    cases_text = cases if cases is not None else "not known"
    stop_value = (f"{stop_text}; {cases_text} cases; largest weight change {_percent(change)}; "
                  f"case {case or 'not known'}")
    lines.append(_line("Stop condition", stop_value))
    lower_text = "not known" if facts["vt_lower_mix_meets"] is None else (
        "yes" if facts["vt_lower_mix_meets"] else "no")
    lines.append(_line("Mix still meets the mandate when VT expected return is one point lower", lower_text))
    if mode == "institution":
        failed_cost = next((row.get("case") for row in payload.get("stress", [])
                            if row.get("group") == "Costs" and not row.get("meets_objective")), None)
        facts["failing_trading_cost"] = failed_cost
        lines.append(_line("Trading cost at which the plan stops meeting the objective",
                           failed_cost or "not known"))


def _check(label: str, value, threshold: str, passes: bool | None, formatter=_percent) -> dict:
    """Return a consistently formatted code-computed member check."""
    result = "not known" if passes is None else "pass" if passes else "fail"
    return {"label": label, "result": result, "measured": formatter(value), "threshold": threshold}


def _vote(checks: list[dict]) -> str:
    """Apply the committee's published vote rules."""
    failures = sum(check["result"] == "fail" for check in checks)
    unknown = any(check["result"] == "not known" for check in checks)
    if unknown and failures <= 1:
        return "Cannot judge"
    if failures >= 2:
        return "Oppose"
    if failures == 1 and not unknown:
        return "Approve with conditions"
    return "Approve"


def committee_checks(mode: str, facts: dict) -> list[dict]:
    """Compute all three members' checks and votes from the fact sheet values."""
    if not facts["has_mix"]:
        stock_label = facts.get("stock_label", "Stocks (VT)")
        unknown_sets = [
            [f"{stock_label} are at least {ENDOWMENT_MINIMUM_STOCK_WEIGHT:.0%}",
             f"Chance of meeting the objective or goal is at least {ENDOWMENT_MINIMUM_CHANCE:.0%}",
             f"Horizon is at least {ENDOWMENT_MINIMUM_HORIZON_YEARS} years"],
            ["Plan ending value is at or above the 60/40 benchmark",
             f"Average monthly turnover is at most {INDEXER_MAXIMUM_TURNOVER:.0%}",
             "Stop condition is not triggered"],
            ["Plan worst backtest drop is no worse than the 60/40 benchmark",
             "A mix still meets the mandate when VT expected return is one point lower",
             "Bad outcome is unlikely"],
        ]
        if facts.get("has_individual_stocks"):
            unknown_sets[0].append("Every individual stock in the plan passes Buffett's checks")
            unknown_sets[2].append("Every individual stock in the plan passes Burry's checks")
        return [{"name": name, "philosophy": _philosophy(name),
                 "checks": [_check(label, None, "not known", None, lambda _: "not known")
                            for label in labels],
                 "vote": "Cannot judge"}
                for name, labels in zip(MEMBER_NAMES, unknown_sets)]
    weights = facts["weights"]
    chance = facts["chance"]
    horizon = facts["horizon_years"]
    endowment = [
        _check(f"{facts.get('stock_label', 'Stocks (VT)')} are at least {ENDOWMENT_MINIMUM_STOCK_WEIGHT:.0%}", facts.get("stock_weight"),
               f"at least {ENDOWMENT_MINIMUM_STOCK_WEIGHT:.2%}",
               None if facts.get("stock_weight") is None else facts["stock_weight"] >= ENDOWMENT_MINIMUM_STOCK_WEIGHT),
        _check(f"Chance of meeting the objective or goal is at least {ENDOWMENT_MINIMUM_CHANCE:.0%}", chance,
               f"at least {ENDOWMENT_MINIMUM_CHANCE:.2%}",
               None if chance is None else chance >= ENDOWMENT_MINIMUM_CHANCE),
        _check(f"Horizon is at least {ENDOWMENT_MINIMUM_HORIZON_YEARS} years", horizon,
               f"at least {ENDOWMENT_MINIMUM_HORIZON_YEARS} years",
               None if horizon is None else horizon >= ENDOWMENT_MINIMUM_HORIZON_YEARS,
               lambda value: f"{value} years" if value is not None else "not known"),
    ]
    if facts.get("has_individual_stocks"):
        results = facts.get("buffett_stock_results", [])
        endowment.append(_check("Every individual stock in the plan passes Buffett's checks", results,
                                "every individual stock passes", None if None in results else all(results),
                                lambda value: "not known" if None in value else f"{sum(value)} of {len(value)} pass"))
    plan_backtest = facts["backtest_plan"]
    benchmark_backtest = facts["backtest_benchmark"]
    plan_end = None if plan_backtest is None else plan_backtest.get(
        "ending_dollar_value", plan_backtest.get("ending_value"))
    benchmark_end = None if benchmark_backtest is None else benchmark_backtest.get(
        "ending_dollar_value", benchmark_backtest.get("ending_value"))
    turnover = facts["average_turnover"]
    triggered = facts["stop"].get("triggered")
    indexer = [
        _check("Plan ending value is at or above the 60/40 benchmark", plan_end, _money(benchmark_end),
               None if plan_end is None or benchmark_end is None else plan_end >= benchmark_end, _money),
        _check(f"Average monthly turnover is at most {INDEXER_MAXIMUM_TURNOVER:.0%}", turnover,
               f"at most {INDEXER_MAXIMUM_TURNOVER:.2%}",
               None if turnover is None else turnover <= INDEXER_MAXIMUM_TURNOVER),
        _check("Stop condition is not triggered", triggered, "stable",
               None if triggered is None else not triggered,
               lambda value: "triggered" if value else "stable" if value is not None else "not known"),
    ]
    plan_drop = None if plan_backtest is None else plan_backtest.get("worst_peak_to_trough_drop")
    benchmark_drop = None if benchmark_backtest is None else benchmark_backtest.get(
        "worst_peak_to_trough_drop")
    downside_value = facts.get("floor_chance") if mode == "institution" else facts.get("p10_ending_value")
    downside_threshold = (f"at most {RISK_MAXIMUM_INSTITUTION_FLOOR_CHANCE:.2%}" if mode == "institution"
                          else _money(facts.get("personal_goal_half")))
    personal_goal_half = facts.get("personal_goal_half")
    if downside_value is None or (mode == "personal" and personal_goal_half is None):
        downside_pass = None
    elif mode == "institution":
        downside_pass = downside_value <= RISK_MAXIMUM_INSTITUTION_FLOOR_CHANCE
    else:
        downside_pass = downside_value >= personal_goal_half
    skeptic = [
        _check("Plan worst backtest drop is no worse than the 60/40 benchmark", plan_drop,
               _percent(benchmark_drop),
               None if plan_drop is None or benchmark_drop is None else plan_drop >= benchmark_drop),
        _check("A mix still meets the mandate when VT expected return is one point lower",
               facts["vt_lower_mix_meets"], "yes", facts["vt_lower_mix_meets"],
               lambda value: "yes" if value else "no" if value is not None else "not known"),
        _check("Bad outcome is unlikely", downside_value, downside_threshold, downside_pass,
               _percent if mode == "institution" else _money),
    ]
    if facts.get("has_individual_stocks"):
        results = facts.get("burry_stock_results", [])
        skeptic.append(_check("Every individual stock in the plan passes Burry's checks", results,
                              "every individual stock passes", None if None in results else all(results),
                              lambda value: "not known" if None in value else f"{sum(value)} of {len(value)} pass"))
    groups = [("Endowment Builder", endowment), ("Indexer", indexer), ("Risk Skeptic", skeptic)]
    return [{"name": name, "philosophy": _philosophy(name), "checks": checks, "vote": _vote(checks)}
            for name, checks in groups]


def _philosophy(name: str) -> str:
    """Give each member's one-sentence public philosophy."""
    philosophies = {
        "Endowment Builder": "Favors long-horizon growth through stocks and broad diversification.",
        "Indexer": "Favors low cost, simplicity, and skepticism of clever optimizers.",
        "Risk Skeptic": "Puts downside first and distrusts estimates.",
    }
    return philosophies[name]


def _rule_summary(member: dict) -> str:
    """Write a short memo entirely from code-generated check descriptions."""
    results = "; ".join(f"{check['label']}: {check['result']}" for check in member["checks"])
    return ("Rule-based summary written by code, not by artificial intelligence. "
            f"Vote: {member['vote']}. Checks: {results}.")


def _saved_memo(mode: str, member: str, lines: list[str]) -> str | None:
    """Load a saved memo only when its adjacent fact sheet matches exactly."""
    safe_member = member.lower().replace(" ", "_")
    fact_path = MEMO_DIRECTORY / f"{mode}_fact_sheet.txt"
    memo_path = MEMO_DIRECTORY / f"{mode}_{safe_member}.md"
    if not fact_path.exists() or not memo_path.exists():
        return None
    if fact_path.read_text(encoding="utf-8").splitlines() != lines:
        return None
    return memo_path.read_text(encoding="utf-8").strip()


def flag_unprinted_numbers(memo: str, printed_lines: list[str]) -> list[str]:
    """Find memo numbers not represented by a displayed fact, allowing normal rounding."""
    pattern = re.compile(r"\$?\d[\d,]*(?:\.\d+)?(?:\s*(?:million|billion|thousand))?%?", re.IGNORECASE)
    printed = [_number_value(match.group()) for line in printed_lines for match in pattern.finditer(line)]
    flags = []
    for match in pattern.finditer(memo):
        token = match.group()
        value, tolerance = _number_value(token)
        if not any(abs(value - candidate) <= tolerance for candidate, _ in printed):
            flags.append(token)
    return flags


def _number_value(token: str) -> tuple[float, float]:
    """Convert a displayed numeric token into a value and rounding allowance."""
    compact = token.lower().replace("$", "").replace(",", "").strip()
    percent = compact.endswith("%")
    compact = compact.rstrip("%").strip()
    multiplier = 1.0
    for word, scale in (("million", 1_000_000), ("billion", 1_000_000_000), ("thousand", 1_000)):
        if compact.endswith(word):
            compact = compact[:-len(word)].strip()
            multiplier = scale
            break
    decimals = len(compact.split(".", 1)[1]) if "." in compact else 0
    value = float(compact) * multiplier
    if percent:
        value /= 100
        multiplier /= 100
    return value, 0.5 * (10 ** -decimals) * multiplier


def member_system_prompt(member: str) -> str:
    """Return the bounded-review instructions for one member."""
    return (f"You are the {member}. {_philosophy(member)} "
            "You give an independent educational committee view.\n\n"
            "Write a memo of at most 180 words to an investment committee. "
            "Your vote has already been decided by the checks and is given to you; "
            "explain it and do not change it. "
            "Use only numbers that appear in the fact sheet, exactly as printed; never compute, estimate or "
            "recall any other number. If a fact is "
            "not known, say it is not known. Do not mention prices or anything outside the fact sheet. Plain "
            "language, no abbreviations. End with one sentence on what would change your vote. This is an "
            "educational exercise, not investment advice.")


def live_review(fact_sheet_lines: list[str], member: str, vote: str = "Cannot judge") -> str:
    """Request an optional Claude memo without reading credentials from the repository."""
    try:
        import anthropic
    except ImportError as error:
        raise RuntimeError("Live review needs the anthropic package and an Anthropic API key in the "
                           "ANTHROPIC_API_KEY environment variable; the saved review still works") from error
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("Live review needs the anthropic package and an Anthropic API key in the "
                           "ANTHROPIC_API_KEY environment variable; the saved review still works")
    try:
        client = anthropic.Anthropic()
        fact_sheet_text_and_vote = "\n".join(fact_sheet_lines) + f"\nVote decided by code: {vote}"
        response = client.beta.messages.create(
            model="claude-opus-5-5",
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "medium"},
            system=member_system_prompt(member),
            messages=[{"role": "user", "content": fact_sheet_text_and_vote}],
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("Live review was refused by the model.")
    except anthropic.AuthenticationError as error:
        raise RuntimeError("Live review could not authenticate the Anthropic API key.") from error
    except anthropic.RateLimitError as error:
        raise RuntimeError("Live review is temporarily rate limited. Please try again later.") from error
    except anthropic.APIStatusError as error:
        raise RuntimeError("Live review service returned an error. Please try again later.") from error
    except anthropic.APIConnectionError as error:
        raise RuntimeError("Live review could not connect to the Anthropic service.") from error
    return "".join(block.text for block in response.content if block.type == "text").strip()


def committee_report(mode: str, payload: dict, live: bool = False) -> dict:
    """Build the public committee response, optionally replacing memos with live reviews."""
    facts, lines = build_fact_sheet(mode, payload)
    if mode == "personal":
        facts["personal_goal_half"] = (payload.get("inputs", {}).get("goal", 0)
                                      * RISK_MINIMUM_PERSONAL_GOAL_FRACTION)
    members = committee_checks(mode, facts)
    for member in members:
        memo = (live_review(lines, member["name"], member["vote"])
                if live else _saved_memo(mode, member["name"], lines))
        member["memo"] = memo or _rule_summary(member)
        member["memo_source"] = "live" if live else "saved" if memo else "rule-based"
        check_lines = [value for check in member["checks"]
                       for value in (check["label"], check["measured"], check["threshold"])]
        member["flagged_numbers"] = flag_unprinted_numbers(member["memo"], lines + check_lines)
    votes = [member["vote"] for member in members]
    tally = {"approve": votes.count("Approve"),
             "approve_with_conditions": votes.count("Approve with conditions"),
             "oppose": votes.count("Oppose"), "cannot_judge": votes.count("Cannot judge")}
    outcome = ("Approve" if tally["approve"] == 3 else "Oppose" if tally["oppose"] >= 2
               else "Approve with conditions")
    return {"fact_sheet_lines": lines, "members": members, "tally": tally, "outcome": outcome}
