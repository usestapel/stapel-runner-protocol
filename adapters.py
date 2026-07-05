"""Harness-adapter interface — the second half of the protocol library.

A *harness adapter* is the seam between the runner and a concrete model<->harness
backend (an SDK session, a subprocess, ...). The contract is deliberately small:

    adapter.open_session(role_spec) -> Session
    Session.turn(prompt)            -> TurnResult   # {text, usage}
    adapter.oneshot(role_spec, prompt) -> TurnResult
    Session.close() / adapter.close()

Usage is **always** the strict five-component :class:`stapel_taskspecs.UsageSplit`
and is validated on every :class:`TurnResult` — that is a protocol condition, not
a convenience (studio-design 7.16). What is deliberately *out of scope* here
(moat): anti-cheat rules, permission policies, concrete system prompts, routing
config. Reference adapters live in :mod:`agent_sdk_adapter` and
:mod:`subprocess_adapter`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from stapel_taskspecs import UsageSplit

__all__ = ["RoleSpec", "TurnResult", "Session", "HarnessAdapter"]


@dataclass
class RoleSpec:
    """The configuration a runner needs to open a session for a role.

    Built from a ``task.assign`` ``invocation`` (see :meth:`from_invocation`).
    Concrete system-prompt *text* is a moat concern: this carries a
    ``system_prompt_ref`` (a pointer resolved elsewhere) and an optional inline
    ``system_prompt`` only for OSS reference/testing.
    """

    role: str = "coder"
    backend: str = ""
    model: str = ""
    #: "per-task" (persistent, append-only) or "one-shot".
    session: str = "per-task"
    system_prompt: str | None = None
    system_prompt_ref: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    llm_base_url: str | None = None
    budget: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_invocation(cls, invocation: dict[str, Any], *, role: str = "coder") -> "RoleSpec":
        """Build a RoleSpec from a ``task.assign`` invocation dict."""
        inv = dict(invocation or {})
        known = {
            "backend", "model", "session", "system_prompt", "system_prompt_ref",
            "allowed_tools", "llm_base_url", "budget",
        }
        return cls(
            role=role,
            backend=inv.get("backend", ""),
            model=inv.get("model", ""),
            session=inv.get("session", "per-task"),
            system_prompt=inv.get("system_prompt"),
            system_prompt_ref=inv.get("system_prompt_ref"),
            allowed_tools=inv.get("allowed_tools", []) or [],
            llm_base_url=inv.get("llm_base_url"),
            budget=inv.get("budget", {}) or {},
            extra={k: v for k, v in inv.items() if k not in known},
        )


@dataclass
class TurnResult:
    """The result of one :meth:`Session.turn` — ``{text, usage}`` plus raw.

    ``usage`` must be a five-component :class:`UsageSplit`; it is validated on
    construction so an adapter cannot silently return a partial split. Supports
    mapping-style access (``result["text"]`` / ``result["usage"]``) so callers
    can treat it as the ``{text, usage}`` the protocol spec names.
    """

    text: str
    usage: UsageSplit
    raw: Any = None

    def __post_init__(self) -> None:
        if not isinstance(self.usage, UsageSplit):
            raise TypeError("TurnResult.usage must be a stapel_taskspecs.UsageSplit")
        self.usage.validate()

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "usage": self.usage.to_dict()}

    def __getitem__(self, key: str) -> Any:
        if key == "text":
            return self.text
        if key == "usage":
            return self.usage
        raise KeyError(key)


class Session(ABC):
    """A live harness session. Persistent by default (append-only, cache-friendly)."""

    @abstractmethod
    def turn(self, prompt: str) -> TurnResult:
        """Send ``prompt`` and return the ``{text, usage}`` result."""

    @abstractmethod
    def close(self) -> None:
        """Release the session's resources. Idempotent."""

    def __enter__(self) -> "Session":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class HarnessAdapter(ABC):
    """Opens sessions for a model<->harness backend."""

    @abstractmethod
    def open_session(self, role_spec: RoleSpec) -> Session:
        """Open a :class:`Session` configured by ``role_spec``."""

    def oneshot(self, role_spec: RoleSpec, prompt: str) -> TurnResult:
        """Open a session, run a single turn, and close it.

        The default drives :meth:`open_session` + one :meth:`Session.turn`; an
        adapter with a cheaper stateless path may override it.
        """
        session = self.open_session(role_spec)
        try:
            return session.turn(prompt)
        finally:
            session.close()

    def close(self) -> None:
        """Release any adapter-level resources. Default no-op; idempotent."""
