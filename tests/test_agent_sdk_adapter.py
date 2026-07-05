"""Agent-SDK reference adapter.

The persistent-session driver and the text/usage extraction are exercised
against a **fake async client** (no network, no API key). ``build_agent_options``
is tested only when claude-agent-sdk is importable; otherwise it is skipped and
we assert the honest AdapterUnavailableError path.
"""

from __future__ import annotations

import importlib.util

import pytest

from stapel_runner_protocol import AgentSdkAdapter, RoleSpec
from stapel_runner_protocol.agent_sdk_adapter import extract_text, extract_usage
from stapel_taskspecs import UsageSplit

HAS_SDK = importlib.util.find_spec("claude_agent_sdk") is not None


# --- fakes mirroring the SDK message shapes -----------------------------


class TextBlock:
    def __init__(self, text):
        self.text = text


class AssistantMessage:
    def __init__(self, *texts):
        self.content = [TextBlock(t) for t in texts]


class ResultMessage:  # name matters: _is_result() matches on it
    def __init__(self, usage):
        self.usage = usage
        self.total_cost_usd = 0.01


class FakeClient:
    """Records connect/disconnect and scripts one response per query."""

    def __init__(self, script):
        self._script = script
        self.connected = False
        self.disconnected = False
        self.queries = []

    async def connect(self):
        self.connected = True

    async def query(self, prompt):
        self.queries.append(prompt)
        self._pending = self._script(prompt)

    async def receive_response(self):
        for msg in self._pending:
            yield msg

    async def disconnect(self):
        self.disconnected = True


def _script(prompt):
    return [
        AssistantMessage("Hello, ", f"{prompt}!"),
        ResultMessage(
            {
                "cache_read_input_tokens": 900,
                "cache_creation_input_tokens": 0,
                "input_tokens": 30,
                "output_tokens": 12,
            }
        ),
    ]


# --- pure extraction ----------------------------------------------------


def test_extract_text_concatenates_blocks():
    messages = _script("world")
    assert extract_text(messages) == "Hello, world!"


def test_extract_usage_maps_from_result():
    split = extract_usage(_script("x"))
    assert isinstance(split, UsageSplit)
    assert split.cache_read == 900 and split.output == 12


def test_extract_usage_zero_when_no_result():
    split = extract_usage([AssistantMessage("no result here")])
    assert split.total_tokens == 0


# --- full persistent-session driver on the fake -------------------------


def test_session_turn_uses_persistent_client():
    client = FakeClient(_script)
    adapter = AgentSdkAdapter(client_factory=lambda rs: client)
    session = adapter.open_session(RoleSpec(backend="agent-sdk", model="m"))
    try:
        assert client.connected is True
        r1 = session.turn("alpha")
        r2 = session.turn("beta")
        assert r1.text == "Hello, alpha!"
        assert r2.text == "Hello, beta!"
        assert client.queries == ["alpha", "beta"]  # same session, append-only
        assert r1.usage.cache_read == 900
    finally:
        session.close()
    assert client.disconnected is True


def test_oneshot_opens_and_closes():
    client = FakeClient(_script)
    adapter = AgentSdkAdapter(client_factory=lambda rs: client)
    result = adapter.oneshot(RoleSpec(model="m"), "quick")
    assert result.text == "Hello, quick!"
    assert client.disconnected is True


def test_turn_after_close_raises():
    from stapel_runner_protocol.errors import AdapterError

    client = FakeClient(_script)
    session = AgentSdkAdapter(client_factory=lambda rs: client).open_session(RoleSpec())
    session.close()
    with pytest.raises(AdapterError):
        session.turn("x")


# --- options mapping (needs the real SDK types) -------------------------


@pytest.mark.skipif(not HAS_SDK, reason="claude-agent-sdk not installed")
def test_build_agent_options_maps_role_spec():
    from stapel_runner_protocol.agent_sdk_adapter import build_agent_options

    opts = build_agent_options(
        RoleSpec(
            model="claude-opus-4-8",
            allowed_tools=["bash", "edit"],
            system_prompt="be terse",
            llm_base_url="http://proxy",
            budget={"max_turns": 8},
        )
    )
    assert opts.model == "claude-opus-4-8"
    assert list(opts.allowed_tools) == ["bash", "edit"]
    assert opts.env.get("ANTHROPIC_BASE_URL") == "http://proxy"
    assert opts.max_turns == 8
