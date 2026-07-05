"""Reference harness adapter: a persistent claude-agent-sdk session.

This is the coder's battle-tested configuration from the vertical slice: one
persistent, append-only SDK session per task (cache_read-friendly). The SDK is
async; this adapter runs a dedicated event loop in a background thread and
drives the client synchronously so it fits the :class:`Session` contract.

``claude-agent-sdk`` is an optional dependency (``pip install
stapel-runner-protocol[agent-sdk]``). If it is not installed the adapter still
imports — it raises :class:`AdapterUnavailableError` only when you try to open a
real session without injecting a ``client_factory``. The pure pieces (options
build, text/usage extraction) and the whole session driver are exercised against
a fake async client, so behaviour is tested without any network or API key.

The adapter drives any async client exposing ``connect()`` / ``query(prompt)`` /
``receive_response()`` (async iterator) / ``disconnect()`` — the shape of
``claude_agent_sdk.ClaudeSDKClient``.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Callable

from .adapters import HarnessAdapter, RoleSpec, Session, TurnResult
from .errors import AdapterError, AdapterUnavailableError
from .usage import usage_from_anthropic

__all__ = [
    "AgentSdkAdapter",
    "AgentSdkSession",
    "build_agent_options",
    "extract_text",
    "extract_usage",
]

#: async client factory: role_spec -> object with connect/query/receive_response/disconnect
ClientFactory = Callable[[RoleSpec], Any]


def _is_result(message: Any) -> bool:
    """True for the terminal ResultMessage of a response turn."""
    return type(message).__name__ == "ResultMessage" or hasattr(message, "total_cost_usd")


def _text_blocks(message: Any) -> list[str]:
    content = getattr(message, "content", None)
    if not content:
        return []
    return [b.text for b in content if hasattr(b, "text") and isinstance(b.text, str)]


def extract_text(messages: list[Any]) -> str:
    """Concatenate the assistant text blocks across a turn's messages."""
    parts: list[str] = []
    for msg in messages:
        parts.extend(_text_blocks(msg))
    return "".join(parts)


def extract_usage(messages: list[Any]):
    """Map the terminal ResultMessage usage onto a :class:`UsageSplit`."""
    from stapel_taskspecs import UsageSplit

    for msg in messages:
        if _is_result(msg):
            usage = getattr(msg, "usage", None)
            if usage is None:
                return UsageSplit().validate()
            return usage_from_anthropic(usage)
    return UsageSplit().validate()


def build_agent_options(role_spec: RoleSpec):
    """Map a :class:`RoleSpec` onto a ``claude_agent_sdk.ClaudeAgentOptions``.

    Imported lazily so this module stays importable without the SDK.
    """
    try:
        from claude_agent_sdk import ClaudeAgentOptions
    except ImportError as exc:  # pragma: no cover - exercised only without the SDK
        raise AdapterUnavailableError(
            "claude-agent-sdk is not installed; `pip install stapel-runner-protocol[agent-sdk]`"
        ) from exc

    kwargs: dict[str, Any] = {}
    if role_spec.model:
        kwargs["model"] = role_spec.model
    if role_spec.allowed_tools:
        kwargs["allowed_tools"] = list(role_spec.allowed_tools)
    if role_spec.system_prompt is not None:
        kwargs["system_prompt"] = role_spec.system_prompt
    if role_spec.llm_base_url:
        kwargs["env"] = {"ANTHROPIC_BASE_URL": role_spec.llm_base_url}
    budget = role_spec.budget or {}
    if "max_budget_usd" in budget:
        kwargs["max_budget_usd"] = budget["max_budget_usd"]
    if "max_turns" in budget:
        kwargs["max_turns"] = budget["max_turns"]
    return ClaudeAgentOptions(**kwargs)


def _default_client_factory(role_spec: RoleSpec) -> Any:
    try:
        from claude_agent_sdk import ClaudeSDKClient
    except ImportError as exc:  # pragma: no cover - exercised only without the SDK
        raise AdapterUnavailableError(
            "claude-agent-sdk is not installed; `pip install stapel-runner-protocol[agent-sdk]`"
        ) from exc
    return ClaudeSDKClient(options=build_agent_options(role_spec))


class _LoopThread:
    """A background asyncio loop that coroutines can be submitted to."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

    def run(self, coro: Any) -> Any:
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    def stop(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)
        self._loop.close()


class AgentSdkSession(Session):
    """A persistent SDK session; each :meth:`turn` is one append to the session."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self._loop = _LoopThread()
        self._closed = False
        try:
            self._loop.run(client.connect())
        except Exception as exc:
            self._loop.stop()
            raise AdapterError(f"failed to connect agent-sdk session: {exc}") from exc

    def turn(self, prompt: str) -> TurnResult:
        if self._closed:
            raise AdapterError("turn() on a closed agent-sdk session")
        messages = self._loop.run(self._collect(prompt))
        return TurnResult(text=extract_text(messages), usage=extract_usage(messages), raw=messages)

    async def _collect(self, prompt: str) -> list[Any]:
        await self._client.query(prompt)
        messages: list[Any] = []
        async for msg in self._client.receive_response():
            messages.append(msg)
            if _is_result(msg):
                break
        return messages

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._loop.run(self._client.disconnect())
        except Exception:
            pass
        finally:
            self._loop.stop()


class AgentSdkAdapter(HarnessAdapter):
    """Open a persistent claude-agent-sdk session per role.

    Inject ``client_factory`` in tests (or to wire a custom SDK client); the
    default builds a real ``ClaudeSDKClient`` and requires the SDK to be
    installed.
    """

    def __init__(self, *, client_factory: ClientFactory | None = None) -> None:
        self._client_factory = client_factory or _default_client_factory

    def open_session(self, role_spec: RoleSpec) -> AgentSdkSession:
        client = self._client_factory(role_spec)
        return AgentSdkSession(client)
