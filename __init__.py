"""stapel-runner-protocol — WS orchestrator<->runner protocol + harness-adapter ABC.

Two halves, both on the OSS side of the OSS/moat boundary (studio-design 2.1):

1. **Protocol** — versioned JSON messages (``hello`` / ``task.assign`` /
   ``task.progress`` / ``task.report`` / ``task.cancel`` / ``ping`` / ``pong``),
   a transport-agnostic encode/decode core, an optional ``websockets`` binding,
   and a sequencing state machine (idempotent progress by ``(task_id, seq)``,
   resume/replay on reconnect; checkpoint = git commit). Task/report schemas are
   **imported** from stapel-taskspecs, not re-invented.
2. **Harness adapters** — an ABC (``open_session`` / ``Session.turn`` /
   ``oneshot`` / ``close``) whose ``turn`` returns ``{text, usage}`` with a
   strict five-component :class:`stapel_taskspecs.UsageSplit`, plus reference
   adapters for claude-agent-sdk (persistent session) and a subprocess JSONL
   harness.

What is deliberately *not* here (moat): anti-cheat rules, permission policies,
concrete system prompts, routing config.

Imports are lazy (PEP 562): ``import stapel_runner_protocol`` pulls in nothing
but the stdlib until a symbol is touched, so ``jsonschema`` / ``websockets`` /
``claude-agent-sdk`` load only when used.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # messages
    "Hello",
    "TaskAssign",
    "TaskProgress",
    "TaskReportMessage",
    "TaskCancel",
    "Ping",
    "Pong",
    "MESSAGES",
    # transport core
    "encode",
    "decode",
    "to_frame",
    # state machine
    "ConnectionState",
    "TaskChannel",
    "OutboxLog",
    "InboxTracker",
    "is_sequenced",
    # adapters
    "RoleSpec",
    "TurnResult",
    "Session",
    "HarnessAdapter",
    "SubprocessAdapter",
    "SubprocessSession",
    "AgentSdkAdapter",
    "AgentSdkSession",
    # usage
    "usage_from_anthropic",
    "usage_from_mapping",
    # validation
    "validate",
    "is_valid",
    "iter_errors",
    "load_schema",
    "message_types",
    "SCHEMA_FILES",
    "SCHEMA_VERSION",
    "PROTOCOL_VERSION",
    # errors
    "RunnerProtocolError",
    "SchemaValidationError",
    "UnknownMessageError",
    "ProtocolStateError",
    "AdapterError",
    "AdapterUnavailableError",
]

_LAZY = {
    "Hello": "messages",
    "TaskAssign": "messages",
    "TaskProgress": "messages",
    "TaskReportMessage": "messages",
    "TaskCancel": "messages",
    "Ping": "messages",
    "Pong": "messages",
    "MESSAGES": "messages",
    "encode": "transport",
    "decode": "transport",
    "to_frame": "transport",
    "ConnectionState": "state",
    "TaskChannel": "state",
    "OutboxLog": "state",
    "InboxTracker": "state",
    "is_sequenced": "state",
    "RoleSpec": "adapters",
    "TurnResult": "adapters",
    "Session": "adapters",
    "HarnessAdapter": "adapters",
    "SubprocessAdapter": "subprocess_adapter",
    "SubprocessSession": "subprocess_adapter",
    "AgentSdkAdapter": "agent_sdk_adapter",
    "AgentSdkSession": "agent_sdk_adapter",
    "usage_from_anthropic": "usage",
    "usage_from_mapping": "usage",
    "validate": "validation",
    "is_valid": "validation",
    "iter_errors": "validation",
    "load_schema": "validation",
    "message_types": "validation",
    "SCHEMA_FILES": "validation",
    "SCHEMA_VERSION": "validation",
    "PROTOCOL_VERSION": "validation",
    "RunnerProtocolError": "errors",
    "SchemaValidationError": "errors",
    "UnknownMessageError": "errors",
    "ProtocolStateError": "errors",
    "AdapterError": "errors",
    "AdapterUnavailableError": "errors",
}


def __getattr__(name: str):
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    mod = importlib.import_module(f".{module}", __name__)
    return getattr(mod, name)


def __dir__() -> list[str]:
    return sorted(__all__)


if TYPE_CHECKING:  # give type checkers/IDEs the real symbols
    from .adapters import HarnessAdapter, RoleSpec, Session, TurnResult
    from .agent_sdk_adapter import AgentSdkAdapter, AgentSdkSession
    from .errors import (
        AdapterError,
        AdapterUnavailableError,
        ProtocolStateError,
        RunnerProtocolError,
        SchemaValidationError,
        UnknownMessageError,
    )
    from .messages import (
        MESSAGES,
        Hello,
        Ping,
        Pong,
        TaskAssign,
        TaskCancel,
        TaskProgress,
        TaskReportMessage,
    )
    from .state import (
        ConnectionState,
        InboxTracker,
        OutboxLog,
        TaskChannel,
        is_sequenced,
    )
    from .subprocess_adapter import SubprocessAdapter, SubprocessSession
    from .transport import decode, encode, to_frame
    from .usage import usage_from_anthropic, usage_from_mapping
    from .validation import (
        PROTOCOL_VERSION,
        SCHEMA_FILES,
        SCHEMA_VERSION,
        is_valid,
        iter_errors,
        load_schema,
        message_types,
        validate,
    )
