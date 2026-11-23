"""Offline checks for Ask Compass. A fake Claude client stands in for the real one, so no key or network is used."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import anthropic
import assistant
import server

PLAN_INPUTS = {"savings": 40000, "monthly_contribution": 1200, "goal": 1000000, "years": 30,
               "tolerated_drop": 0.40, "monthly_expenses": 3000, "reserve_months": 6}


class FakeMessages:
    """Replays a scripted list of responses and records every request."""

    def __init__(self, script):
        self.script = list(script)
        self.requests = []

    def create(self, **request):
        # Copy the message list: the assistant keeps appending to the same list after each call.
        self.requests.append({**request, "messages": list(request["messages"])})
        return self.script.pop(0)


def fake_client(script):
    messages = FakeMessages(script)
    return SimpleNamespace(beta=SimpleNamespace(messages=messages)), messages


def tool_call(name, arguments, call_id="call_1"):
    block = SimpleNamespace(type="tool_use", name=name, input=arguments, id=call_id)
    return SimpleNamespace(content=[block], stop_reason="tool_use", model=assistant.MODEL)


def answer(text):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn", model=assistant.MODEL)


@pytest.fixture(autouse=True)
def key_and_sessions(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    assistant._sessions.clear()
    yield
    # Plans built here must not leak into later test files through the server's cache.
    server.personal_cached.cache_clear()


def test_status_reports_built_in_mode_without_a_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    body = TestClient(server.app).get("/api/assistant/status").json()
    assert body["available"] is False
    assert body["mode"] == "built-in"


def test_built_in_mode_reruns_the_plan_for_a_what_if(monkeypatch):
    """Without a key, 'what if I add $200 a month' re-runs the real plan and every number checks out."""
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    body = TestClient(server.app).post("/api/assistant/chat", json={
        "message": "What if I add $200 a month?", "page_data": {"plan_inputs": PLAN_INPUTS}}).json()
    assert body["mode"] == "built-in"
    assert "40.5%" in body["reply"]  # the pinned default plan's chance of reaching the goal
    assert "$1,400" in body["reply"]
    assert body["actions"][0]["inputs"]["monthly_contribution"] == 1400
    assert body["unverified_numbers"] == []


def test_built_in_mode_defines_terms_and_falls_back_to_help(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    client = TestClient(server.app)
    definition = client.post("/api/assistant/chat", json={"message": "What is a Sharpe ratio?"}).json()
    assert "return earned above cash" in definition["reply"]
    unknown = client.post("/api/assistant/chat", json={"message": "tell me a joke"}).json()
    assert "built-in assistant" in unknown["reply"]


def test_built_in_mode_reads_typed_portfolios():
    import assistant_offline
    assert assistant_offline.holdings_from_text("60% VT 40% BND on $250,000") == {"VT": 150000.0, "BND": 100000.0}
    assert assistant_offline.holdings_from_text("Analyze 50000 VTI, 30000 VXUS, 20000 BND") == {
        "VTI": 50000.0, "VXUS": 30000.0, "BND": 20000.0}
    assert assistant_offline.holdings_from_text("$40k in VOO and $10k in QQQ") == {"VOO": 40000.0, "QQQ": 10000.0}
    assert assistant_offline.holdings_from_text("What is a Sharpe ratio?") is None


def test_tool_loop_runs_the_real_engine_and_checks_numbers(monkeypatch):
    plan = server.personal_endpoint(server.PersonalRequest(**PLAN_INPUTS))
    chance = plan["portfolios"][0]["simulation"]["chance_of_goal"]
    real_number = f"{chance * 100:.1f}%"
    client, messages = fake_client([
        tool_call("build_personal_plan", PLAN_INPUTS),
        answer(f"Your chance of reaching the goal is {real_number}. A made-up figure is 63.9%."),
    ])
    monkeypatch.setattr(anthropic, "Anthropic", lambda: client)
    body = TestClient(server.app).post("/api/assistant/chat", json={"message": "Will I make it?"}).json()
    assert body["steps"][0] == {"tool": "build_personal_plan", "input": PLAN_INPUTS, "ok": True}
    assert body["actions"][0]["action"] == "plan"
    # The tool result handed back to the model carries the engine's own number.
    tool_result = messages.requests[1]["messages"][-1]["content"][0]
    assert real_number in tool_result["content"]
    # The real number passes the check; the invented one is flagged.
    assert "63.9%" in body["unverified_numbers"]
    assert real_number not in body["unverified_numbers"]
    # Requests use the default model with server-side refusal fallbacks.
    assert messages.requests[0]["model"] == "claude-opus-5-5"
    assert messages.requests[0]["fallbacks"] == "default"


def test_tool_error_goes_back_to_the_model(monkeypatch):
    client, messages = fake_client([
        tool_call("stock_screen", {"ticker": "!!bad"}),
        answer("That ticker is not valid."),
    ])
    monkeypatch.setattr(anthropic, "Anthropic", lambda: client)
    body = TestClient(server.app).post("/api/assistant/chat", json={"message": "Screen !!bad"}).json()
    assert body["steps"][0]["ok"] is False
    tool_result = messages.requests[1]["messages"][-1]["content"][0]
    assert tool_result["is_error"] is True


def test_conversation_continues_in_the_same_session(monkeypatch):
    client, messages = fake_client([answer("Hello."), answer("Still here.")])
    monkeypatch.setattr(anthropic, "Anthropic", lambda: client)
    app = TestClient(server.app)
    first = app.post("/api/assistant/chat", json={"message": "Hi"}).json()
    app.post("/api/assistant/chat", json={"message": "Again", "session_id": first["session_id"]})
    assert len(messages.requests[1]["messages"]) == 3  # user, assistant, user


def test_failed_turn_is_rolled_back(monkeypatch):
    def broken():
        raise anthropic.APIConnectionError(request=None)

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=lambda **_: broken())))
    monkeypatch.setattr(anthropic, "Anthropic", lambda: client)
    response = TestClient(server.app).post("/api/assistant/chat", json={"message": "Hi", "session_id": None})
    assert response.status_code == 503
    assert all(not session["messages"] for session in assistant._sessions.values())


def test_page_context_counts_as_printed_numbers(monkeypatch):
    client, _ = fake_client([answer("The page shows a risk score of 7 and a value of $250,000.")])
    monkeypatch.setattr(anthropic, "Anthropic", lambda: client)
    body = TestClient(server.app).post("/api/assistant/chat", json={
        "message": "Summarize", "page": "Analyze",
        "context_lines": ["Risk score: 7 of 10", "Total value: $250,000"]}).json()
    assert body["unverified_numbers"] == []
