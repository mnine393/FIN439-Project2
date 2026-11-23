"""Personal savings planning using the shared Compass mix engine."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import ceil

import numpy as np
import pandas as pd

from mandate import BENCHMARK_WEIGHTS, FUNDS, Mandate, TOLERANCE
from mixes import first_lowest_volatility, mix_statistics
from portfolio import estimate_from_monthly_returns, portfolio_metrics, search_portfolio
from universe import DEFAULT_UNIVERSE, Fund, benchmark_weights


@dataclass(frozen=True)
class PersonalInputs:
    """Inputs supplied by a personal-planning client."""
    savings: float
    monthly_contribution: float
    goal: float
    years: int
    tolerated_drop: float
    monthly_expenses: float
    reserve_months: int
    holdings: tuple[float, float, float, float] | None = None
    other_cash: float = 0.0
    trading_cost_basis_points: float = 10.0
    seed: int = 439
    max_single_stock_weight: float | None = None
    max_individual_stocks_total: float | None = None
    min_holdings: int | None = None


def emergency_reserve(inputs: PersonalInputs) -> dict:
    """Set aside the emergency reserve before calculating investments."""
    target = inputs.reserve_months * inputs.monthly_expenses
    set_aside = min(inputs.savings, target)
    shortfall = target - set_aside
    if shortfall == 0:
        months_to_fund = 0
        message = None
    elif inputs.monthly_contribution > 0:
        months_to_fund = int(ceil(shortfall / inputs.monthly_contribution))
        message = None
    else:
        months_to_fund = None
        message = "The emergency reserve cannot be funded because monthly contribution is zero."
    return {"reserve_target": float(target), "amount_set_aside_now": float(set_aside),
            "shortfall": float(shortfall), "months_to_fund": months_to_fund,
            "invested_starting_amount": float(max(0.0, inputs.savings - target)), "message": message}


def future_value(starting_amount: float, contribution: float, months: int, rate: float,
                 contribution_delay: int = 0) -> float:
    """Calculate end value for month-end contributions at a yearly quoted rate."""
    monthly_rate = rate / 12
    growth = (1 + monthly_rate) ** months
    contribution_months = max(0, months - contribution_delay)
    if abs(monthly_rate) < 1e-14:
        annuity = contribution_months
    else:
        annuity = ((1 + monthly_rate) ** contribution_months - 1) / monthly_rate
    return starting_amount * growth + contribution * annuity


def required_real_return(savings: float, contribution: float, goal: float, years: int,
                         contribution_delay: int = 0) -> float | None:
    """Find the annual real return needed to meet a goal, capped at 30 percent."""
    months = years * 12
    if months <= 0:
        raise ValueError("Years to the goal must be greater than zero.")
    if future_value(savings, contribution, months, 0.0, contribution_delay) >= goal:
        return 0.0
    if future_value(savings, contribution, months, 0.30, contribution_delay) < goal:
        return None
    lower = 0.0
    upper = 0.30
    for _ in range(60):
        middle = (lower + upper) / 2
        if future_value(savings, contribution, months, middle, contribution_delay) >= goal:
            upper = middle
        else:
            lower = middle
    return upper


def build_mandate(inputs: PersonalInputs, inflation: float) -> tuple[Mandate, str | None]:
    """Build a compatibility mandate describing the personal return objective."""
    reserve = emergency_reserve(inputs)
    required = required_real_return(reserve["invested_starting_amount"], inputs.monthly_contribution,
                                    inputs.goal, inputs.years, reserve["months_to_fund"] or 0)
    objective = required if required is not None else 0.30
    legacy_reserve_weight = 0.0 if inputs.savings == 0 else min(
        1.0, reserve["reserve_target"] / inputs.savings
    )
    mandate = Mandate("Personal plan", reserve["invested_starting_amount"],
                      "fixed required real return plus inflation", required_real_return=objective,
                      horizon_years=inputs.years, minimum_reserve_weight=legacy_reserve_weight,
                      reserve_funds=("SGOV",),
                      maximum_fund_weight=None, worst_12_month_drop_limit=inputs.tolerated_drop,
                      cash_flow_amount=inputs.monthly_contribution,
                      cash_flow_frequency="monthly contribution", benchmark_weights=BENCHMARK_WEIGHTS)
    note = "not reachable at any realistic return" if required is None else reserve["message"]
    return mandate, note


def personal_verdicts(weights: np.ndarray, expected_return: float, worst_return: float,
                      objective: float | None, tolerated_drop: float) -> list[dict]:
    """Report the four personal mandate rules in plain language."""
    return [
        {"rule": "Long-only", "pass": bool(np.min(weights) >= -TOLERANCE),
         "measured_value": float(np.min(weights)), "limit": 0.0},
        {"rule": "Weights sum to 100%", "pass": bool(abs(weights.sum() - 1) <= TOLERANCE),
         "measured_value": float(weights.sum()), "limit": 1.0},
        {"rule": "Expected return at least the objective",
         "pass": objective is not None and expected_return >= objective - TOLERANCE,
         "measured_value": float(expected_return), "limit": objective},
        {"rule": "Worst rolling 12-month return no worse than tolerated drop",
         "pass": bool(worst_return >= -tolerated_drop - TOLERANCE), "measured_value": float(worst_return),
         "limit": -tolerated_drop},
    ]


def mix_row(index: int, statistics: dict[str, np.ndarray], objective: float | None,
            tolerated_drop: float) -> dict:
    """Turn a vectorized mix row into a serializable portfolio record."""
    weights = statistics["weights"][index]
    expected = float(statistics["expected_return"][index])
    worst = float(statistics["worst_12_month_return"][index])
    return {"weights": tuple(float(value) for value in weights), "expected_return": expected,
            "volatility": float(statistics["volatility"][index]), "worst_12_month_return": worst,
            "verdicts": personal_verdicts(weights, expected, worst, objective, tolerated_drop)}


def choose_personal_mix(statistics: dict[str, np.ndarray], objective: float | None,
                        tolerated_drop: float) -> dict | None:
    """Select the first least-volatile mix passing every personal rule."""
    if objective is None:
        return None
    mask = ((statistics["expected_return"] >= objective - TOLERANCE) &
            (statistics["worst_12_month_return"] >= -tolerated_drop - TOLERANCE))
    index = first_lowest_volatility(mask, statistics)
    return None if index is None else mix_row(index, statistics, objective, tolerated_drop)


def _draw_returns(monthly_returns: pd.DataFrame, weights, inflation: float, inputs: PersonalInputs,
                  paths: int, draws: np.ndarray | None = None, tickers=FUNDS) -> tuple[np.ndarray, np.ndarray]:
    """Draw whole historical months so all fund returns remain paired."""
    source = monthly_returns.loc[:, list(tickers)].to_numpy(float) @ np.asarray(weights)
    if draws is None:
        generator = np.random.default_rng(inputs.seed)
        draws = generator.integers(0, len(source), size=(paths, inputs.years * 12))
    return source[draws] - inflation / 12, draws


def personal_simulation(monthly_returns, weights, inflation, inputs, paths: int = 10_000,
                        draws: np.ndarray | None = None, tickers=FUNDS) -> dict:
    """Bootstrap real dollar paths, adding contributions after reserve funding completes."""
    returns, draws = _draw_returns(monthly_returns, weights, inflation, inputs, paths, draws, tickers)
    reserve = emergency_reserve(inputs)
    delay = reserve["months_to_fund"]
    values = np.empty((paths, returns.shape[1] + 1), dtype=float)
    values[:, 0] = reserve["invested_starting_amount"]
    for month in range(returns.shape[1]):
        values[:, month + 1] = values[:, month] * (1 + returns[:, month])
        if delay is not None and month + 1 > delay:
            values[:, month + 1] += inputs.monthly_contribution
    ending = values[:, -1]
    bands = [{"month": month, "p10": float(np.percentile(values[:, month], 10)),
              "p25": float(np.percentile(values[:, month], 25)),
              "p50": float(np.percentile(values[:, month], 50)),
              "p75": float(np.percentile(values[:, month], 75)),
              "p90": float(np.percentile(values[:, month], 90))}
             for month in range(values.shape[1])]
    return {"chance_of_goal": float(np.mean(ending >= inputs.goal)),
            "p10_ending_value": float(np.percentile(ending, 10)),
            "median_ending_value": float(np.percentile(ending, 50)),
            "p90_ending_value": float(np.percentile(ending, 90)),
            "bands": bands, "draws": draws}


def contribution_for_80_percent(monthly_returns, weights, inflation, inputs, tickers=FUNDS):
    """Use fixed bootstrap draws to find the least contribution for an 80 percent chance."""
    reserve = emergency_reserve(inputs)
    if reserve["months_to_fund"] is None:
        return "not reachable"
    returns, _ = _draw_returns(monthly_returns, weights, inflation, inputs, 10_000, tickers=tickers)
    factors = np.cumprod(1 + returns[:, ::-1], axis=1)[:, ::-1]
    start_value = reserve["invested_starting_amount"] * factors[:, 0]
    delay = reserve["months_to_fund"]
    contribution_factor = np.zeros(len(start_value))
    for month in range(delay, returns.shape[1]):
        contribution_factor += factors[:, month + 1] if month + 1 < returns.shape[1] else 1
    def chance(contribution: float) -> float:
        return float(np.mean(start_value + contribution * contribution_factor >= inputs.goal))
    if chance(50_000) < 0.80:
        return "not reachable"
    lower = 0.0
    upper = 50_000.0
    for _ in range(30):
        middle = (lower + upper) / 2
        if chance(middle) >= 0.80:
            upper = middle
        else:
            lower = middle
    return float(round(upper / 25) * 25)


def _ways(inputs: PersonalInputs, statistics: dict[str, np.ndarray], reserve: dict,
          inflation: float) -> list[dict]:
    """Calculate three one-input ways to create a feasible plan."""
    required = required_real_return(reserve["invested_starting_amount"], inputs.monthly_contribution,
                                    inputs.goal, inputs.years, reserve["months_to_fund"] or 0)
    def input_object(**change) -> dict:
        """Return complete website inputs with exactly one proposed change."""
        values = asdict(inputs)
        if inputs.holdings is not None:
            values["holdings"] = dict(zip(FUNDS, inputs.holdings))
        values.update(change)
        return values

    def row(change: str, result: float | int | str, new_inputs: dict, explanation: str) -> dict:
        """Build one website-ready feasibility option."""
        return {"change": change, "result": result, "new_inputs": new_inputs,
                "explanation": explanation}

    if choose_personal_mix(statistics, None if required is None else required + inflation,
                           inputs.tolerated_drop) is not None:
        return [
            row("Keep your monthly contribution unchanged", "already works", input_object(),
                "Your current monthly contribution already allows a mix that meets your rules."),
            row("Keep your time horizon unchanged", "already works", input_object(),
                "Your current time horizon already allows a mix that meets your rules."),
            row("Keep your tolerated drop unchanged", "already works", input_object(),
                "Your current tolerated drop already allows a mix that meets your rules."),
        ]

    def feasible(contribution: float, years: int, drop: float) -> bool:
        trial_inputs = PersonalInputs(
            savings=inputs.savings,
            monthly_contribution=contribution,
            goal=inputs.goal,
            years=years,
            tolerated_drop=drop,
            monthly_expenses=inputs.monthly_expenses,
            reserve_months=inputs.reserve_months,
            holdings=inputs.holdings,
            other_cash=inputs.other_cash,
            trading_cost_basis_points=inputs.trading_cost_basis_points,
            seed=inputs.seed,
        )
        trial_reserve = emergency_reserve(trial_inputs)
        trial = required_real_return(trial_reserve["invested_starting_amount"], contribution, inputs.goal, years,
                                     trial_reserve["months_to_fund"] or 0)
        objective = None if trial is None else trial + inflation
        return choose_personal_mix(statistics, objective, drop) is not None
    contribution_result: float | str = "not reachable"
    if feasible(50_000, inputs.years, inputs.tolerated_drop):
        lower = inputs.monthly_contribution
        upper = 50_000.0
        while lower + 25 < upper:
            middle = round(((lower + upper) / 2) / 25) * 25
            if feasible(middle, inputs.years, inputs.tolerated_drop):
                upper = middle
            else:
                lower = middle
        contribution_result = float(round(upper / 25) * 25)
    years_result: int | str = "not reachable"
    for extra_years in range(1, 31):
        if feasible(inputs.monthly_contribution, inputs.years + extra_years, inputs.tolerated_drop):
            years_result = extra_years
            break
    drop_result: float | str = "not reachable"
    if required is not None and required + inflation <= statistics["expected_return"].max() + TOLERANCE:
        for percent in range(int(np.ceil(inputs.tolerated_drop * 100)), 101):
            if feasible(inputs.monthly_contribution, inputs.years, percent / 100):
                drop_result = percent / 100
                break
    contribution_inputs = input_object(monthly_contribution=contribution_result) if isinstance(
        contribution_result, float) else input_object()
    years_inputs = input_object(years=inputs.years + years_result) if isinstance(
        years_result, int
    ) else input_object()
    drop_inputs = input_object(tolerated_drop=drop_result) if isinstance(
        drop_result, float
    ) else input_object()
    return [
        row("Increase your monthly contribution", contribution_result, contribution_inputs,
            "This is the smallest $25 monthly contribution increase that allows a mix to meet your rules."
            if isinstance(contribution_result, float) else
            "Even a much larger monthly contribution cannot make a mix meet your current rules."),
        row("Add years to your time horizon", years_result, years_inputs,
            "This is the fewest extra whole years that allows a mix to meet your rules."
            if isinstance(years_result, int) else
            "Adding up to 30 years cannot make a mix meet your current rules."),
        row("Allow a larger tolerated drop", drop_result, drop_inputs,
            "This is the smallest whole-percent tolerated drop that allows a mix to meet your rules."
            if isinstance(drop_result, float) else
            "The return objective, rather than the drop limit, prevents a mix from meeting your rules."),
    ]


def trades(weights, inputs: PersonalInputs, invested_amount: float | None = None, tickers=FUNDS):
    """Produce funded per-fund trades using plan weights."""
    holdings = np.asarray(inputs.holdings or tuple(0.0 for _ in tickers), dtype=float)
    total = float(holdings.sum() + inputs.other_cash)
    if inputs.holdings is None:
        total = inputs.savings + inputs.monthly_contribution + inputs.other_cash
        if invested_amount is not None:
            total = invested_amount
    targets = np.asarray(weights) * total
    changes = targets - holdings
    return [{"fund": fund, "target_dollars": float(target), "buy_or_sell_dollars": float(change),
             "estimated_cost_dollars": float(abs(change) * inputs.trading_cost_basis_points / 10_000)}
            for fund, target, change in zip(tickers, targets, changes)]


def policy_statement(inputs: PersonalInputs, reserve: dict, required: float | None, inflation: float,
                     stop_threshold: float) -> list[dict]:
    """Return website-ready investment-policy sections."""
    objective = None if required is None else required + inflation
    purpose = (f"You plan to reach ${inputs.goal:,.0f} in today's dollars. This keeps the goal meaningful "
               "after inflation rather than treating future dollars as equal to today's dollars.")
    horizon = (f"You plan to invest for {inputs.years} years and add ${inputs.monthly_contribution:,.0f} "
               "each month. The horizon determines how long your savings and contributions have to compound.")
    return_objective = ("You cannot reach this goal at a realistic return with these inputs. You should use "
                        "one of the proposed changes before relying on an investment mix." if objective is None else
                        f"You need a {required:.2%} annual return after inflation, which is a {objective:.2%} "
                        f"annual nominal objective with current {inflation:.2%} inflation. This objective links "
                        f"your ${inputs.goal:,.0f} goal, contributions, and {inputs.years}-year horizon to a "
                        "measurable portfolio rule.")
    reserve_paragraph = (f"You plan to keep ${reserve['reserve_target']:,.0f} aside for "
                         f"{inputs.reserve_months} months of ${inputs.monthly_expenses:,.0f} monthly expenses. "
                         "This reserve prevents an emergency from forcing you to sell invested assets at an "
                         "unfavorable time.")
    risk = (f"You plan to reject mixes whose worst rolling twelve-month return was below "
            f"{-inputs.tolerated_drop:.0%}. This limit reflects the largest historical loss you said you can "
            "tolerate while staying invested.")
    return [
        {"title": "Purpose and goal", "paragraph": purpose},
        {"title": "Time horizon", "paragraph": horizon},
        {"title": "Return objective", "paragraph": return_objective},
        {"title": "Emergency reserve", "paragraph": reserve_paragraph},
        {"title": "Risk limit", "paragraph": risk},
        {"title": "Permitted investments", "paragraph": "You plan to use SGOV for Treasury bills, IEF for "
         "Treasury bonds, USIG for investment-grade bonds, and VT for global stocks. These four funds give "
         "the plan liquid building blocks with different expected return and risk roles."},
        {"title": "Benchmark", "paragraph": "You plan to compare results with a 60% VT and 40% IEF "
         "benchmark. The comparison shows whether the selected mix earns its added complexity relative to a "
         "simple global-stock and bond allocation."},
        {"title": "Monitoring", "paragraph": f"You plan to review the allocation each year and reopen the "
         f"plan if a stress case changes a weight by more than {stop_threshold:.0%}. This rule keeps the "
         "plan responsive when estimates or your circumstances materially change."},
        {"title": "Statements", "paragraph": "You should treat this as educational planning, not personalized "
         "investment advice. You can review the separate disclosure describing how artificial intelligence "
         "assisted with the code."},
    ]


def personal_backtest(inputs: PersonalInputs, monthly_returns: pd.DataFrame, inflation: float,
                      required_real: float | None, funds: tuple[Fund, ...] = DEFAULT_UNIVERSE) -> dict:
    """Run an expanding-window actual-dollar backtest without looking ahead."""
    if tuple(funds) != DEFAULT_UNIVERSE:
        return _custom_personal_backtest(inputs, monthly_returns, inflation, required_real, tuple(funds))
    values = monthly_returns.loc[:, list(FUNDS)].reset_index(drop=True)
    months = pd.to_datetime(monthly_returns["month"]).reset_index(drop=True)
    available_years = max(0, (len(values) - 36) // 12)
    years = min(inputs.years, available_years)
    if years == 0:
        return {"message": "Not enough history for a 36-month warm-up backtest.", "values_are": "actual dollars"}
    reserve = emergency_reserve(inputs)
    start = 35
    end = min(len(values) - 1, start + years * 12)
    # Each decision uses only the Consumer Price Index vintage available at that
    # month-end.  Synthetic or uncovered dates retain the caller's fallback.
    from cpi_signal import load_cpi_vintages
    try:
        # Asking the shared loader for its saved panel avoids downloading data for
        # arbitrary synthetic dates; dates absent from that panel use the fallback.
        vintage_frame, _ = load_cpi_vintages([])
        inflation_by_date = dict(zip(vintage_frame["decision_date"].dt.date, vintage_frame["inflation"]))
    except (FileNotFoundError, ValueError):
        inflation_by_date = {}
    value_by_name = {"Your plan": reserve["invested_starting_amount"], "Equal weight": reserve["invested_starting_amount"],
                     "60/40 benchmark": reserve["invested_starting_amount"]}
    prior_weights = {name: None for name in value_by_name}
    histories = {name: [] for name in value_by_name}
    plan_weights = []
    unreachable_months = 0
    for index in range(start, end):
        statistics = mix_statistics(values.iloc[:index + 1])
        month_end = (months.iloc[index] + pd.offsets.MonthEnd(0)).date()
        known_inflation = inflation_by_date.get(month_end, inflation)
        objective = None if required_real is None else required_real + known_inflation
        choice = choose_personal_mix(statistics, objective, inputs.tolerated_drop)
        if choice is None:
            permitted = statistics["worst_12_month_return"] >= -inputs.tolerated_drop - TOLERANCE
            candidates = np.flatnonzero(permitted)
            choice_weights = statistics["weights"][candidates[np.argmax(statistics["expected_return"][candidates])]] if len(candidates) else np.full(4, .25)
            unreachable_months += 1
        else:
            choice_weights = np.asarray(choice["weights"])
        current = {"Your plan": choice_weights, "Equal weight": np.full(4, .25),
                   "60/40 benchmark": np.asarray(BENCHMARK_WEIGHTS)}
        asset_returns = values.iloc[index + 1].to_numpy(float)
        for name, weights in current.items():
            turnover = 0.0 if prior_weights[name] is None else float(np.abs(weights - prior_weights[name]).sum() / 2)
            gross = float(asset_returns @ weights)
            value_by_name[name] *= 1 + gross - turnover * inputs.trading_cost_basis_points / 10_000
            if reserve["months_to_fund"] is not None and index - start + 1 > reserve["months_to_fund"]:
                value_by_name[name] += inputs.monthly_contribution
            histories[name].append({"month": months.iloc[index + 1], "value": value_by_name[name],
                                    "turnover": turnover})
            prior_weights[name] = weights * (1 + asset_returns) / (1 + gross)
        plan_weights.append({"month": months.iloc[index + 1], **dict(zip(FUNDS, choice_weights))})
    total_contributed = max(0, len(histories["Your plan"]) - (reserve["months_to_fund"] or 0)) * inputs.monthly_contribution
    ending_values = {name: value for name, value in value_by_name.items()}
    summary = []
    for name, history in histories.items():
        values_for_name = np.asarray([row["value"] for row in history], dtype=float)
        drawdowns = values_for_name / np.maximum.accumulate(values_for_name) - 1
        summary.append({"portfolio": name, "ending_value": float(value_by_name[name]),
                        "total_contributed": float(total_contributed),
                        "worst_peak_to_trough_drop": float(drawdowns.min()),
                        "objective_not_reachable_months": unreachable_months if name == "Your plan" else 0,
                        "average_turnover": float(np.mean([row["turnover"] for row in history]))})
    return {"values_are": "actual dollars", "monthly_values": histories, "plan_weights": plan_weights,
            "total_contributed": total_contributed, "ending_values": ending_values,
            "objective_not_reachable_months": unreachable_months, "summary": summary,
            "years_covered": years}


def _custom_personal_backtest(inputs, monthly_returns, inflation, required_real, funds):
    """Expanding-window custom backtest, re-optimizing quarterly for large universes."""
    tickers = tuple(f.ticker for f in funds)
    values = monthly_returns.loc[:, list(tickers)].reset_index(drop=True)
    months = pd.to_datetime(monthly_returns["month"]).reset_index(drop=True)
    years = min(inputs.years, max(0, (len(values) - 36) // 12))
    if not years:
        return {"message": "Not enough history for a 36-month warm-up backtest.", "values_are": "actual dollars",
                "monthly_values": {}, "plan_weights": [], "summary": []}
    reserve, start, end = emergency_reserve(inputs), 35, min(len(values) - 1, 35 + years * 12)
    benchmark = np.asarray(benchmark_weights(funds))
    # The plan holds the benchmark until a mix meets the rules (those months are counted as "not reachable").
    mixes = {"Your plan": benchmark, "Equal weight": np.full(len(funds), 1 / len(funds)), "60/40 benchmark": benchmark}
    balances = {name: reserve["invested_starting_amount"] for name in mixes}; prior = {name: None for name in mixes}
    histories = {name: [] for name in mixes}; plan_weights = []; last_plan = None; unreachable = 0
    for index in range(start, end):
        if last_plan is None or len(funds) <= 8 or (index - start) % 3 == 0:
            choice, *_ = _custom_selector(inputs, values.iloc[:index + 1], inflation, funds, required_real,
                                           step=.05 if len(funds) <= 8 else .10)
            if choice is None: unreachable += 1
            else: last_plan = np.asarray(choice["weights"])
        if last_plan is not None: mixes["Your plan"] = last_plan
        asset_returns = values.iloc[index + 1].to_numpy(float)
        for name, weights in mixes.items():
            turnover = 0.0 if prior[name] is None else float(np.abs(weights - prior[name]).sum() / 2)
            gross = float(asset_returns @ weights)
            balances[name] *= 1 + gross - turnover * inputs.trading_cost_basis_points / 10_000
            if reserve["months_to_fund"] is not None and index - start + 1 > reserve["months_to_fund"]:
                balances[name] += inputs.monthly_contribution
            histories[name].append({"month": months.iloc[index + 1], "value": balances[name], "turnover": turnover})
            prior[name] = weights * (1 + asset_returns) / (1 + gross)
        if last_plan is not None: plan_weights.append({"month": months.iloc[index + 1], **dict(zip(tickers, last_plan))})
    contributed = max(0, end - start - (reserve["months_to_fund"] or 0)) * inputs.monthly_contribution
    summary = []
    for name, history in histories.items():
        path = np.asarray([row["value"] for row in history]); drawdown = path / np.maximum.accumulate(path) - 1
        summary.append({"portfolio": name, "ending_value": float(balances[name]), "total_contributed": float(contributed),
                        "worst_peak_to_trough_drop": float(drawdown.min()),
                        "objective_not_reachable_months": unreachable if name == "Your plan" else 0,
                        "average_turnover": float(np.mean([row["turnover"] for row in history]))})
    return {"values_are": "actual dollars", "monthly_values": histories, "plan_weights": plan_weights,
            "total_contributed": contributed, "ending_values": balances, "objective_not_reachable_months": unreachable,
            "summary": summary, "years_covered": years,
            "rebalancing": "quarterly" if len(funds) > 8 else "monthly"}


def _custom_selector(inputs, monthly_returns, inflation, funds, required, *, step=.05):
    """Select a custom-universe personal mix; cash is outside the portfolio."""
    tickers = tuple(fund.ticker for fund in funds)
    estimates = estimate_from_monthly_returns(monthly_returns, "all history", tickers)
    mandate = Mandate("Personal plan", emergency_reserve(inputs)["invested_starting_amount"],
                      objective_kind="fixed required real return plus inflation",
                      required_real_return=required, horizon_years=inputs.years,
                      minimum_reserve_weight=0.0, reserve_funds=(), maximum_fund_weight=None,
                      worst_12_month_drop_limit=inputs.tolerated_drop,
                      max_single_stock_weight=getattr(inputs, "max_single_stock_weight", None),
                      max_individual_stocks_total=getattr(inputs, "max_individual_stocks_total", None),
                      min_holdings=getattr(inputs, "min_holdings", None))
    objective = None if required is None else required + inflation
    def checker(weights, expected):
        rules = mandate.check(weights, {"expected_return": expected,
                              "monthly_returns": estimates["monthly_returns"]}, inflation, funds)
        # A reserve is carved out before investing, so it is deliberately not an allocation rule.
        return [rule for rule in rules if rule["rule"] != "Emergency reserve"]
    selected = None if objective is None else search_portfolio(estimates, checker, mandate, inflation, funds, step)
    return selected, estimates, mandate, checker, objective


def _custom_ways(inputs, values, inflation, funds, settings):
    """Find one-change feasibility options without exploding optimizer requests."""
    tickers = tuple(f.ticker for f in funds)
    coarse = len(funds) > 8
    contribution_step = 100 if coarse else 25
    drop_step = 5 if coarse else 1
    def changed(**updates):
        return PersonalInputs(**{**asdict(inputs), **updates})
    def feasible(trial):
        reserve = emergency_reserve(trial)
        required = required_real_return(reserve["invested_starting_amount"], trial.monthly_contribution,
                                        trial.goal, trial.years, reserve["months_to_fund"] or 0)
        selected, *_ = _custom_selector(trial, values, inflation, funds, required, step=settings)
        return selected is not None
    def input_data(trial):
        return asdict(trial)
    current = feasible(inputs)
    if current:
        return [{"change": label, "result": "already works", "new_inputs": input_data(inputs),
                 "explanation": "Your current inputs already allow a mix that meets your rules."}
                for label in ("Keep your monthly contribution unchanged", "Keep your time horizon unchanged",
                              "Keep your tolerated drop unchanged")]
    contribution = "not reachable"
    if feasible(changed(monthly_contribution=50_000)):
        low, high = inputs.monthly_contribution, 50_000.0
        while high - low > contribution_step:
            middle = round(((low + high) / 2) / contribution_step) * contribution_step
            if feasible(changed(monthly_contribution=middle)): high = middle
            else: low = middle
        contribution = float(high)
    years = "not reachable"
    for extra in range(1, 31):
        if feasible(changed(years=inputs.years + extra)):
            years = extra; break
    drop = "not reachable"
    for percent in range(int(np.ceil(inputs.tolerated_drop * 100)), 101, drop_step):
        if feasible(changed(tolerated_drop=percent / 100)):
            drop = percent / 100; break
    rows = [("Increase your monthly contribution", contribution, "monthly_contribution"),
            ("Add years to your time horizon", years, "years"),
            ("Allow a larger tolerated drop", drop, "tolerated_drop")]
    output = []
    for label, value, field in rows:
        trial = inputs if value == "not reachable" else changed(**{field: inputs.years + value if field == "years" else value})
        output.append({"change": label, "result": value, "new_inputs": input_data(trial),
                       "explanation": "This is the smallest tested change that allows a mix to meet your rules."
                       if value != "not reachable" else "This change cannot make a mix meet your current rules."})
    return output


def _plan_custom(inputs, monthly_returns, inflation, funds, stop_threshold, *, step=.05):
    """The personal engine for an arbitrary, role-described investment universe."""
    tickers = tuple(fund.ticker for fund in funds)
    values = monthly_returns.loc[:, list(tickers)]
    reserve = emergency_reserve(inputs)
    required = required_real_return(reserve["invested_starting_amount"], inputs.monthly_contribution,
                                    inputs.goal, inputs.years, reserve["months_to_fund"] or 0)
    selected, estimates, mandate, checker, objective = _custom_selector(inputs, values, inflation, funds, required, step=step)
    specs = [("Equal weight", np.full(len(funds), 1 / len(funds))), ("60/40 benchmark", np.asarray(benchmark_weights(funds)))]
    if selected is not None: specs.insert(0, ("Your plan", np.asarray(selected["weights"])))
    portfolios, plan_simulation = [], None
    for name, weights in specs:
        expected, volatility = portfolio_metrics(weights, estimates)
        from mixes import mix_statistic
        worst = mix_statistic(values, weights)[2]
        simulation = personal_simulation(values, weights, inflation, inputs, tickers=tickers)
        row = {"name": name, "weights": tuple(weights), "expected_return": expected, "volatility": volatility,
               "worst_12_month_return": worst, "verdicts": checker(weights, expected),
               "dollars": dict(zip(tickers, weights * reserve["invested_starting_amount"])),
               "simulation": {key: value for key, value in simulation.items() if key not in ("bands", "draws")}}
        portfolios.append(row)
        if name == "Your plan": plan_simulation = simulation
    if selected is None:
        portfolios.insert(0, {"name": "Your plan", "weights": None, "message": "No mix meets the mandate"})
    # Do not re-run an expensive optimizer merely to establish that the selected mix works.
    if selected is not None:
        ways = [{"change": label, "result": "already works", "new_inputs": asdict(inputs),
                 "explanation": "Your current inputs already allow a mix that meets your rules."}
                for label in ("Keep your monthly contribution unchanged", "Keep your time horizon unchanged",
                              "Keep your tolerated drop unchanged")]
    else:
        ways = _custom_ways(inputs, values, inflation, funds, step)
    return {"inputs": asdict(inputs), "emergency_reserve": reserve, "required_real_return": required,
            "objective": objective, "portfolios": portfolios, "frontier": [], "ways_to_make_it_work": ways,
            "fan_chart": None if plan_simulation is None else plan_simulation["bands"],
            "contribution_for_80_percent": None if selected is None else contribution_for_80_percent(values, selected["weights"], inflation, inputs, tickers=tickers),
            "trades": [] if selected is None else trades(selected["weights"], inputs, reserve["invested_starting_amount"], tickers),
            "trade_message": None if selected is not None else "No mix meets the mandate",
            "policy_statement": policy_statement(inputs, reserve, required, inflation, stop_threshold),
            "selected": selected, "statistics": estimates, "mandate": mandate, "checker": checker}


def plan(inputs: PersonalInputs, monthly_returns: pd.DataFrame, inflation: float,
         stop_threshold: float = 0.20, funds: tuple[Fund, ...] = DEFAULT_UNIVERSE,
         step: float = .05) -> dict:
    """Build the complete fast personal plan, leaving service response shaping to the caller."""
    if tuple(funds) != DEFAULT_UNIVERSE:
        return _plan_custom(inputs, monthly_returns, inflation, tuple(funds), stop_threshold, step=step)
    values = monthly_returns.loc[:, list(FUNDS)]
    statistics = mix_statistics(values)
    reserve = emergency_reserve(inputs)
    required = required_real_return(reserve["invested_starting_amount"], inputs.monthly_contribution,
                                    inputs.goal, inputs.years, reserve["months_to_fund"] or 0)
    objective = None if required is None else required + inflation
    selected = choose_personal_mix(statistics, objective, inputs.tolerated_drop)
    portfolio_specs = [("Equal weight", np.full(4, .25)), ("60/40 benchmark", np.asarray(BENCHMARK_WEIGHTS))]
    if selected is not None:
        portfolio_specs.insert(0, ("Your plan", np.asarray(selected["weights"])))
    portfolios = []
    plan_simulation = None
    for name, weights in portfolio_specs:
        index = int(np.where(np.all(np.isclose(statistics["weights"], weights), axis=1))[0][0])
        row = mix_row(index, statistics, objective, inputs.tolerated_drop)
        simulation = personal_simulation(values, weights, inflation, inputs)
        row.update({"name": name, "dollars": dict(zip(FUNDS, weights * reserve["invested_starting_amount"])),
                    "simulation": {key: value for key, value in simulation.items() if key not in ("bands", "draws")}})
        if name == "Your plan":
            plan_simulation = simulation
        portfolios.append(row)
    if selected is None:
        portfolios.insert(0, {"name": "Your plan", "weights": None,
                              "message": "No mix meets the mandate"})
    frontier = []
    for index in range(len(statistics["weights"])):
        row = mix_row(index, statistics, objective, inputs.tolerated_drop)
        frontier.append({"weights": dict(zip(FUNDS, row["weights"])), "expected_return": row["expected_return"],
                         "volatility": row["volatility"], "worst_12_month_return": row["worst_12_month_return"],
                         "meets_mandate": all(item["pass"] for item in row["verdicts"])})
    return {"inputs": asdict(inputs), "emergency_reserve": reserve, "required_real_return": required,
            "objective": objective, "portfolios": portfolios, "frontier": frontier,
            "ways_to_make_it_work": _ways(inputs, statistics, reserve, inflation),
            "fan_chart": None if plan_simulation is None else plan_simulation["bands"],
            "contribution_for_80_percent": None if selected is None else contribution_for_80_percent(values, selected["weights"], inflation, inputs),
            "trades": [] if selected is None else trades(selected["weights"], inputs, reserve["invested_starting_amount"]),
            "trade_message": None if selected is not None else "No mix meets the mandate",
            "policy_statement": policy_statement(inputs, reserve, required, inflation, stop_threshold),
            "selected": selected, "statistics": statistics}
