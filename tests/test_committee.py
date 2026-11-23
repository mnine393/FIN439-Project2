"""Tests for the code-computed AI Investment Committee."""
import pytest
from fastapi.testclient import TestClient

from committee import _vote, flag_unprinted_numbers, live_review
from server import app, institution_cached


def test_pinned_institution_committee_votes():
    """Keep the required committee decision tied to the pinned institution results."""
    committee = institution_cached()["committee"]
    votes = {member["name"]: member["vote"] for member in committee["members"]}
    assert votes == {
        "Endowment Builder": "Approve with conditions",
        "Indexer": "Oppose",
        "Risk Skeptic": "Oppose",
    }
    assert committee["outcome"] == "Oppose"


@pytest.mark.parametrize(
    ("results", "vote"),
    [(["pass", "pass", "pass"], "Approve"), (["pass", "pass", "fail"], "Approve with conditions"),
     (["pass", "fail", "fail"], "Oppose"), (["pass", "pass", "not known"], "Cannot judge")],
)
def test_vote_rules(results, vote):
    """Apply the published vote rule to every required combination."""
    assert _vote([{"result": result} for result in results]) == vote


def test_number_flag_uses_only_printed_facts():
    """Accept displayed and normally rounded values while flagging a new percentage."""
    lines = ["Chance of meeting the objective: 47.23%", "Median ending value: $134,296,207"]
    assert flag_unprinted_numbers("The chance is 47.23% and value is $134.3 million.", lines) == []
    assert flag_unprinted_numbers("The chance is 47.23%, not 40.0%.", lines) == ["40.0%"]


def test_rule_based_memos_accept_member_check_numbers_and_flag_new_ones(monkeypatch, tmp_path):
    """Member thresholds are allowed, but a number outside their evidence is not."""
    import committee
    monkeypatch.setattr(committee, "MEMO_DIRECTORY", tmp_path)
    institution_cached.cache_clear()
    client = TestClient(app)
    personal = client.post("/api/personal/plan", json={
        "savings": 40_000, "monthly_contribution": 1_200, "goal": 1_000_000,
        "years": 30, "tolerated_drop": .40, "monthly_expenses": 3_000, "reserve_months": 6,
    }).json()["committee"]
    institution = institution_cached()["committee"]
    for report in (personal, institution):
        for member in report["members"]:
            assert member["memo_source"] == "rule-based"
            assert member["flagged_numbers"] == []
    member = personal["members"][0]
    evidence = personal["fact_sheet_lines"] + [
        value for check in member["checks"] for value in (check["label"], check["measured"], check["threshold"])
    ]
    assert flag_unprinted_numbers(member["memo"] + " Extra 40.0%.", evidence) == ["40.0%"]


def test_personal_example_uses_backtest_summary_for_real_committee_votes():
    """The personal fact sheet reads its summary rows and no member is left unable to judge."""
    response = TestClient(app).post("/api/personal/plan", json={
        "savings": 40_000, "monthly_contribution": 1_200, "goal": 1_000_000,
        "years": 30, "tolerated_drop": .40, "monthly_expenses": 3_000, "reserve_months": 6,
    })
    assert response.status_code == 200
    committee = response.json()["committee"]
    assert all("not known" not in line for line in committee["fact_sheet_lines"] if "backtest" in line.lower())
    assert "Average monthly turnover: not known" not in committee["fact_sheet_lines"]
    assert "Total contributed in the backtest: not known" not in committee["fact_sheet_lines"]
    assert all(member["vote"] != "Cannot judge" for member in committee["members"])


def test_institution_fact_sheet_uses_full_history_worst_rolling_return():
    """The constrained plan's risk line is based on its actual full-history mix."""
    committee = institution_cached()["committee"]
    line = next(line for line in committee["fact_sheet_lines"]
                if line.startswith("Worst 12-month return:"))
    assert line != "Worst 12-month return: not known"


def test_live_review_without_credentials_returns_plain_api_message(monkeypatch):
    """Do not contact the network when a local key is unavailable."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="Live review needs the anthropic package"):
        live_review([], "Indexer")
    response = TestClient(app).post("/api/committee/live", json={"mode": "institution", "settings": {}})
    assert response.status_code == 503
    assert "Live review needs the anthropic package" in response.json()["detail"]


def test_no_plan_personal_committee_cannot_judge():
    """A missing feasible personal mix leaves every member unable to judge."""
    payload = {"inputs": {"goal": 1_000_000, "years": 1}, "objective": {},
               "portfolios": [{"name": "Your plan", "weights": None}], "backtest": {},
               "stress": {}, "stop_condition": {}}
    from committee import committee_report
    committee = committee_report("personal", payload)
    assert [member["vote"] for member in committee["members"]] == ["Cannot judge"] * 3
