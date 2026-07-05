"""Harness-adapter ABC contract + usage validation, exercised on a fake."""

from __future__ import annotations

import pytest

from stapel_runner_protocol import HarnessAdapter, RoleSpec, Session, TurnResult
from stapel_taskspecs import UsageSplit


class FakeSession(Session):
    def __init__(self, role_spec):
        self.role_spec = role_spec
        self.turns = []
        self.closed = False

    def turn(self, prompt):
        self.turns.append(prompt)
        return TurnResult(
            text=f"echo:{prompt}",
            usage=UsageSplit(cache_read=10, output=5),
        )

    def close(self):
        self.closed = True


class FakeAdapter(HarnessAdapter):
    def __init__(self):
        self.sessions = []

    def open_session(self, role_spec):
        session = FakeSession(role_spec)
        self.sessions.append(session)
        return session


def test_role_spec_from_invocation():
    rs = RoleSpec.from_invocation(
        {"backend": "agent-sdk", "model": "m", "allowed_tools": ["bash"], "custom": 1},
        role="coder",
    )
    assert rs.role == "coder" and rs.model == "m" and rs.allowed_tools == ["bash"]
    assert rs.extra == {"custom": 1}


def test_turn_returns_text_and_usage():
    result = FakeAdapter().open_session(RoleSpec()).turn("hi")
    assert result.text == "echo:hi"
    assert result["text"] == "echo:hi"  # mapping-style access
    assert isinstance(result["usage"], UsageSplit)
    assert result.to_dict()["usage"]["cache_read"] == 10


def test_turn_result_rejects_non_usagesplit():
    with pytest.raises(TypeError):
        TurnResult(text="x", usage={"cache_read": 1})  # must be a UsageSplit


def test_turn_result_validates_usage():
    # A hand-built partial split must fail on construction.
    bad = UsageSplit()
    object.__setattr__(bad, "output", -1)
    with pytest.raises(Exception):
        TurnResult(text="x", usage=bad)


def test_oneshot_opens_runs_and_closes():
    adapter = FakeAdapter()
    result = adapter.oneshot(RoleSpec(), "one-shot prompt")
    assert result.text == "echo:one-shot prompt"
    assert adapter.sessions[0].closed is True  # oneshot closed the session


def test_session_context_manager_closes():
    session = FakeAdapter().open_session(RoleSpec())
    with session as s:
        s.turn("a")
    assert session.closed is True
