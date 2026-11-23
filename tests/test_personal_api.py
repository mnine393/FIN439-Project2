import pytest
import numpy as np
import pandas as pd
from personal import (PersonalInputs, required_real_return, build_mandate, emergency_reserve,
                      personal_simulation, contribution_for_80_percent, trades, plan,
                      personal_backtest)
from mixes import mix_statistics
from data import load_monthly_returns
from server import app

def test_required_return_known_answer():
    assert required_real_return(100, 0, 121, 2) == pytest.approx(((1.21 ** (1/24))-1)*12, abs=1e-7)


def test_required_return_zero_and_annuity_cases():
    assert required_real_return(1_000, 0, 900, 5) == 0
    rate = .06
    goal = 200 * (((1 + rate / 12) ** 24 - 1) / (rate / 12))
    assert required_real_return(0, 200, goal, 2) == pytest.approx(rate, abs=1e-7)

def test_personal_reserve_and_trade_accounting():
    inputs = PersonalInputs(1000, 100, 5000, 5, .4, 100, 6)
    mandate, _ = build_mandate(inputs, .03)
    assert mandate.minimum_reserve_weight == pytest.approx(.6)
    rows = trades((.6,.1,.1,.2), inputs)
    assert sum(row["buy_or_sell_dollars"] for row in rows) == pytest.approx(1100)


def test_reserve_carve_out_cases_and_trade_cash_accounting():
    funded = emergency_reserve(PersonalInputs(25_000, 500, 1, 1, .4, 3_000, 6))
    assert funded["amount_set_aside_now"] == 18_000
    assert funded["invested_starting_amount"] == 7_000
    assert funded["months_to_fund"] == 0
    short = emergency_reserve(PersonalInputs(10_000, 500, 1, 1, .4, 3_000, 6))
    assert short["shortfall"] == 8_000
    assert short["months_to_fund"] == 16
    assert short["invested_starting_amount"] == 0
    inputs = PersonalInputs(0, 0, 1, 1, .4, 0, 0, holdings=(100, 200, 300, 400), other_cash=50)
    assert sum(row["buy_or_sell_dollars"] for row in trades((.25,) * 4, inputs)) == pytest.approx(50)

def test_personal_drop_limit_is_reported():
    returns, _ = load_monthly_returns(); inputs = PersonalInputs(10_000, 0, 20_000, 5, .01, 0, 0)
    mandate, _ = build_mandate(inputs, .03)
    verdicts = mandate.check((0, 0, 0, 1), {"expected_return": .10, "monthly_returns": returns[["SGOV", "IEF", "USIG", "VT"]]}, .03)
    assert not next(v for v in verdicts if v["rule"] == "Largest 12-month drop")["pass"]

def test_no_mix_has_three_one_change_options():
    from personal import plan
    returns, _ = load_monthly_returns()
    result = plan(PersonalInputs(1, 0, 1_000_000_000, 1, 0, 0, 0), returns, .0335)
    assert len(result["ways_to_make_it_work"]) == 3


def test_ways_to_make_it_work_rebuilds_the_exact_no_plan_case():
    returns, _ = load_monthly_returns()
    inputs = PersonalInputs(25_000, 500, 1_000_000, 35, .35, 3_000, 6)
    result = plan(inputs, returns, .0335)
    assert result["portfolios"][0]["weights"] is None
    options = result["ways_to_make_it_work"]
    assert all({"change", "result", "new_inputs", "explanation"} <= option.keys() for option in options)
    for option in options:
        assert option["result"] != "already works"
        if option["result"] == "not reachable":
            continue
        changed = PersonalInputs(**option["new_inputs"])
        rebuilt = plan(changed, returns, .0335)
        assert rebuilt["selected"] is not None
    contribution = options[0]["result"]
    if contribution != "not reachable":
        lower = PersonalInputs(25_000, contribution - 25, 1_000_000, 35, .35, 3_000, 6)
        assert plan(lower, returns, .0335)["selected"] is None
    extra_years = options[1]["result"]
    if extra_years != "not reachable":
        shorter = PersonalInputs(25_000, 500, 1_000_000, 35 + extra_years - 1, .35, 3_000, 6)
        assert plan(shorter, returns, .0335)["selected"] is None


def test_vectorized_statistics_match_single_mix_statistics():
    from mixes import mix_statistic
    returns, _ = load_monthly_returns()
    statistics = mix_statistics(returns[list(("SGOV", "IEF", "USIG", "VT"))])
    generator = np.random.default_rng(439)
    for index in generator.choice(len(statistics["weights"]), size=20, replace=False):
        weights = statistics["weights"][index]
        expected, volatility, worst = mix_statistic(returns[["SGOV", "IEF", "USIG", "VT"]], weights)
        assert statistics["expected_return"][index] == pytest.approx(expected)
        assert statistics["volatility"][index] == pytest.approx(volatility)
        assert statistics["worst_12_month_return"][index] == pytest.approx(worst)

def test_personal_simulation_is_repeatable_and_80_percent_target():
    returns, _ = load_monthly_returns(); inputs = PersonalInputs(25_000, 500, 1_000_000, 35, .35, 3000, 6)
    one = personal_simulation(returns, (0,.1,.3,.6), .0335, inputs, paths=1000)
    two = personal_simulation(returns, (0,.1,.3,.6), .0335, inputs, paths=1000)
    assert one["median_ending_value"] == two["median_ending_value"]


def test_custom_personal_plan_funds_reserve_shortfall_and_uses_real_returns(monkeypatch):
    """Custom universes use the same delayed-contribution, inflation-adjusted engine."""
    from universe import Fund
    import personal
    funds = tuple(Fund(f"F{index}", role="cash" if index == 0 else "government bonds") for index in range(6))
    returns = pd.DataFrame({"month": pd.date_range("2020-01-01", periods=24, freq="MS"),
                            **{fund.ticker: .01 for fund in funds}})
    inputs = PersonalInputs(0, 100, 100, 1, .9, 100, 1)
    monkeypatch.setattr(personal, "search_portfolio", lambda *args, **kwargs: {
        "weights": (1, 0, 0, 0, 0, 0), "expected_return": .12, "volatility": 0, "method": "grid"})
    result = plan(inputs, returns, .12, funds=funds)
    assert result["emergency_reserve"]["months_to_fund"] == 1
    # Inflation exactly offsets the nominal return: eleven contributions arrive after month one.
    assert result["portfolios"][0]["simulation"]["median_ending_value"] == pytest.approx(1_100)


def test_ten_holding_custom_plan_has_ways_and_a_personal_fan_chart(monkeypatch):
    from universe import Fund
    import personal
    funds = tuple(Fund(f"F{index}", role="cash" if index == 0 else "government bonds") for index in range(10))
    returns = pd.DataFrame({"month": pd.date_range("2018-01-01", periods=48, freq="MS"),
                            **{fund.ticker: .01 for fund in funds}})
    inputs = PersonalInputs(1_000, 0, 1_000, 1, .9, 0, 0)
    monkeypatch.setattr(personal, "search_portfolio", lambda *args, **kwargs: {
        "weights": (1,) + (0,) * 9, "expected_return": .12, "volatility": 0, "method": "optimizer"})
    result = plan(inputs, returns, .02, funds=funds, step=.10)
    assert len(result["ways_to_make_it_work"]) == 3
    assert result["fan_chart"] and {"p10", "p25", "p50", "p75", "p90"} <= result["fan_chart"][0].keys()


def test_80_percent_contribution_resimulates_near_80_percent():
    returns, _ = load_monthly_returns()
    inputs = PersonalInputs(40_000, 1_200, 1_000_000, 30, .20, 3_000, 6)
    contribution = contribution_for_80_percent(returns, (0, .15, .15, .70), .0335, inputs)
    changed = PersonalInputs(40_000, contribution, 1_000_000, 30, .40, 3_000, 6)
    chance = personal_simulation(returns, (0, .15, .15, .70), .0335, changed)["chance_of_goal"]
    assert .79 <= chance <= .82


def test_personal_backtest_does_not_use_later_returns():
    import pandas as pd
    months = pd.date_range("2010-01-01", periods=84, freq="MS")
    index = np.arange(len(months))
    base = pd.DataFrame({"month": months, "SGOV": .001 + index * .000001,
                         "IEF": .002 + np.sin(index) * .0005,
                         "USIG": .003 + np.cos(index) * .0007,
                         "VT": .004 + np.sin(index * 1.7) * .002})
    inputs = PersonalInputs(1_000, 0, 2_000, 4, .50, 0, 0)
    middle = 20
    original = personal_backtest(inputs, base, .01, .01)["plan_weights"][middle]
    changed = base.copy()
    changed.loc[original["month"] < changed["month"], ["SGOV", "IEF", "USIG", "VT"]] = 9.0
    altered = personal_backtest(inputs, changed, .01, .01)["plan_weights"][middle]
    assert original == altered


def test_personal_backtest_summary_reports_average_turnover():
    """Every personal strategy reports the mean of its recorded monthly turnover."""
    returns, _ = load_monthly_returns()
    inputs = PersonalInputs(40_000, 1_200, 1_000_000, 30, .40, 3_000, 6)
    result = personal_backtest(inputs, returns, .0335, .045)
    for row in result["summary"]:
        turnovers = [month["turnover"] for month in result["monthly_values"][row["portfolio"]]]
        assert row["average_turnover"] == pytest.approx(np.mean(turnovers))


def test_pinned_personal_example():
    returns, _ = load_monthly_returns()
    inputs = PersonalInputs(40_000, 1_200, 1_000_000, 30, .40, 3_000, 6)
    result = plan(inputs, returns, .03353016322755642)
    selected = result["selected"]
    portfolio = result["portfolios"][0]
    assert result["emergency_reserve"]["invested_starting_amount"] == 22_000
    assert result["required_real_return"] == pytest.approx(.0452, abs=.0001)
    assert selected["weights"] == pytest.approx((0, .15, .15, .70))
    assert portfolio["expected_return"] == pytest.approx(.0790, abs=.0001)
    assert portfolio["volatility"] == pytest.approx(.1226, abs=.0001)
    assert portfolio["worst_12_month_return"] == pytest.approx(-.1947, abs=.0001)
    assert portfolio["simulation"]["chance_of_goal"] == pytest.approx(.4054, abs=.0001)
    assert result["contribution_for_80_percent"] == 2_025


def test_personal_stress_changes_when_tolerated_drop_changes():
    from server import personal_stress
    returns, _ = load_monthly_returns()
    inputs = PersonalInputs(40_000, 1_200, 1_000_000, 30, .20, 3_000, 6)
    result = plan(inputs, returns, .0335)
    rows, _ = personal_stress(result, inputs, returns, .0335)
    assert len([row for row in rows if row["group"] == "Estimates"]) == 8
    tolerated_drop_rows = [row for row in rows if row["group"] == "Rules" and "Tolerated drop" in row["case"]]
    assert len(tolerated_drop_rows) == 2
    lowered, raised = tolerated_drop_rows
    assert lowered["weights"] != raised["weights"] or lowered["meets_objective"] != raised["meets_objective"]


def test_default_personal_request_has_pinned_goal_chance():
    from fastapi.testclient import TestClient
    response = TestClient(app).post("/api/personal/plan", json={"savings": 40000, "monthly_contribution": 1200,
        "goal": 1000000, "years": 30, "tolerated_drop": .40, "monthly_expenses": 3000, "reserve_months": 6})
    assert response.status_code == 200
    assert response.json()["portfolios"][0]["simulation"]["chance_of_goal"] == pytest.approx(.4054, abs=.0001)

def test_api_health_and_bad_personal_input():
    from fastapi.testclient import TestClient
    client = TestClient(app)
    assert client.get("/api/health").status_code == 200
    assert client.post("/api/personal/plan", json={"savings": -1}).status_code == 422


def test_home_page_and_its_local_assets_are_served():
    from fastapi.testclient import TestClient
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    for path in ("/vendor/plotly.min.js", "/css/compass.css", "/js/app.js"):
        assert path in response.text
        assert client.get(path).status_code == 200


def test_institution_api_is_json_safe_and_keeps_pinned_mix():
    from fastapi.testclient import TestClient
    client = TestClient(app)
    response = client.get("/api/institution")
    assert response.status_code == 200
    payload = response.json()
    selected = next(row for row in payload["portfolios"] if row["name"] == "Constrained portfolio")
    assert selected["weights"] == {"SGOV": 0.0, "IEF": 0.1, "USIG": 0.3, "VT": 0.6}
    assert selected["expected_return"] == pytest.approx(.0736, abs=.0001)
    assert selected["volatility"] == pytest.approx(.1123, abs=.0001)
