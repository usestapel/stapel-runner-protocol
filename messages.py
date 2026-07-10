"""Dataclass models for the runner-protocol v1 messages.

Every message is a small dataclass with the taskspecs affordances:

* :meth:`from_dict` — tolerant parse; unknown keys land in ``extra`` (forward
  compatibility), ``schema_version`` defaults to the current major.
* :meth:`to_dict` — round-trip to a plain JSON-able dict, re-merging ``extra``
  and omitting empty optional fields; ``schema_version`` and ``type`` are
  always stamped.
* :meth:`validate` / :meth:`parse` — schema validation via
  :mod:`stapel_runner_protocol.validation`, plus, for the two messages that
  embed a stapel-taskspecs artifact, validation of that artifact against the
  taskspecs schema (the schemas are *imported*, never re-invented).

The wire ``type`` string is the ``ARTIFACT`` on each class and the key in
:data:`MESSAGES`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from .validation import PROTOCOL_VERSION

__all__ = [
    "Hello",
    "TaskAssign",
    "TaskProgress",
    "TaskReportMessage",
    "TaskCancel",
    "Ping",
    "Pong",
    "MESSAGES",
    "PROTOCOL_VERSION",
]


def _split_extra(data: dict[str, Any], known: tuple[str, ...]) -> dict[str, Any]:
    """Return the subset of ``data`` whose keys are neither known nor reserved."""
    reserved = set(known) | {"schema_version", "type"}
    return {k: v for k, v in data.items() if k not in reserved}


def _prune(d: dict[str, Any]) -> dict[str, Any]:
    """Drop keys whose value is None or an empty list/dict (keep 0 / '' / False)."""
    return {k: v for k, v in d.items() if v is not None and v != [] and v != {}}


class _Message:
    """Mixin providing validate()/parse() over a subclass ``to_dict``."""

    ARTIFACT: ClassVar[str]

    def to_dict(self) -> dict[str, Any]:  # pragma: no cover - overridden
        raise NotImplementedError

    def validate(self):
        """Validate the message envelope (and any embedded taskspecs artifact).

        Embedded-artifact failures (a bad TaskSpec/TaskReport/UsageSplit, raised
        by stapel-taskspecs) are re-wrapped as this package's
        :class:`~stapel_runner_protocol.errors.SchemaValidationError` so callers
        catch a single error taxonomy.
        """
        from stapel_taskspecs import SchemaValidationError as _TaskSpecsError

        from .errors import SchemaValidationError
        from .validation import validate

        validate(self.to_dict(), self.ARTIFACT)
        try:
            self._validate_embedded()
        except _TaskSpecsError as exc:
            raise SchemaValidationError(
                f"{self.ARTIFACT}: embedded taskspecs artifact failed validation ({exc})",
                errors=list(getattr(exc, "errors", []) or []),
            ) from exc
        return self

    def _validate_embedded(self) -> None:
        """Hook for messages that embed a stapel-taskspecs artifact."""

    @classmethod
    def parse(cls, data: dict[str, Any], *, validate: bool = True):
        """from_dict + (optionally) schema validation in one call."""
        obj = cls.from_dict(data)  # type: ignore[attr-defined]
        if validate:
            obj.validate()
        return obj


# --------------------------------------------------------------------------
# control frames


@dataclass
class Hello(_Message):
    ARTIFACT: ClassVar[str] = "hello"
    _KNOWN: ClassVar[tuple[str, ...]] = (
        "protocol_version", "project_id", "runner_version", "capabilities", "resume",
    )

    project_id: str = ""
    runner_version: str = ""
    protocol_version: int = PROTOCOL_VERSION
    capabilities: list[str] = field(default_factory=list)
    #: reconnect: task_id -> last seq contiguously received from the hub.
    resume: dict[str, int] = field(default_factory=dict)
    schema_version: int = 1
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Hello":
        return cls(
            project_id=data.get("project_id", ""),
            runner_version=data.get("runner_version", ""),
            protocol_version=data.get("protocol_version", PROTOCOL_VERSION),
            capabilities=data.get("capabilities", []) or [],
            resume=data.get("resume", {}) or {},
            schema_version=data.get("schema_version", 1),
            extra=_split_extra(data, cls._KNOWN),
        )

    def to_dict(self) -> dict[str, Any]:
        out = {
            "schema_version": self.schema_version,
            "type": self.ARTIFACT,
            "protocol_version": self.protocol_version,
            "project_id": self.project_id,
            "runner_version": self.runner_version,
            "capabilities": self.capabilities,
            "resume": self.resume,
        }
        return {**_prune(out), **self.extra}


@dataclass
class Ping(_Message):
    ARTIFACT: ClassVar[str] = "ping"
    _KNOWN: ClassVar[tuple[str, ...]] = ("nonce", "sent_at")

    nonce: str | int | None = None
    sent_at: str | float | None = None
    schema_version: int = 1
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Ping":
        return cls(
            nonce=data.get("nonce"),
            sent_at=data.get("sent_at"),
            schema_version=data.get("schema_version", 1),
            extra=_split_extra(data, cls._KNOWN),
        )

    def to_dict(self) -> dict[str, Any]:
        out = {
            "schema_version": self.schema_version,
            "type": self.ARTIFACT,
            "nonce": self.nonce,
            "sent_at": self.sent_at,
        }
        return {**_prune(out), **self.extra}


@dataclass
class Pong(_Message):
    ARTIFACT: ClassVar[str] = "pong"
    _KNOWN: ClassVar[tuple[str, ...]] = ("nonce",)

    nonce: str | int | None = None
    schema_version: int = 1
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Pong":
        return cls(
            nonce=data.get("nonce"),
            schema_version=data.get("schema_version", 1),
            extra=_split_extra(data, cls._KNOWN),
        )

    def to_dict(self) -> dict[str, Any]:
        out = {
            "schema_version": self.schema_version,
            "type": self.ARTIFACT,
            "nonce": self.nonce,
        }
        return {**_prune(out), **self.extra}

    @classmethod
    def answer(cls, ping: "Ping") -> "Pong":
        """Build the Pong that answers ``ping`` (echoing its nonce)."""
        return cls(nonce=ping.nonce)


# --------------------------------------------------------------------------
# hub -> runner


@dataclass
class TaskAssign(_Message):
    ARTIFACT: ClassVar[str] = "task.assign"
    _KNOWN: ClassVar[tuple[str, ...]] = (
        "task_id", "task", "role", "invocation", "seq", "attempt",
    )

    task_id: str = ""
    task: dict[str, Any] = field(default_factory=dict)
    role: str = ""
    invocation: dict[str, Any] = field(default_factory=dict)
    seq: int = 0
    #: G-4: the attempt this assign belongs to (0 = unset/legacy). Carried
    #: through by the runner onto every task.progress/task.report it emits
    #: for the run, so the hub can scope inbound idempotency per (task,
    #: attempt, seq) instead of (task, seq) alone — a runner recreated for a
    #: new attempt restarts its own outbound seq at 1, which would otherwise
    #: collide with the PRIOR attempt's already-recorded seqs.
    attempt: int = 0
    schema_version: int = 1
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskAssign":
        task = data.get("task", {}) or {}
        return cls(
            task_id=data.get("task_id") or task.get("id", ""),
            task=task,
            role=data.get("role", ""),
            invocation=data.get("invocation", {}) or {},
            seq=data.get("seq", 0),
            attempt=data.get("attempt", 0),
            schema_version=data.get("schema_version", 1),
            extra=_split_extra(data, cls._KNOWN),
        )

    def to_dict(self) -> dict[str, Any]:
        out = {
            "schema_version": self.schema_version,
            "type": self.ARTIFACT,
            "task_id": self.task_id,
            "task": self.task,
            "role": self.role,
            "invocation": self.invocation,
            "seq": self.seq,
            "attempt": self.attempt,
        }
        return {**_prune(out), **self.extra}

    @property
    def task_spec(self):
        """The embedded task as a :class:`stapel_taskspecs.TaskSpec` model."""
        from stapel_taskspecs import TaskSpec

        return TaskSpec.from_dict(self.task)

    def _validate_embedded(self) -> None:
        from stapel_taskspecs import validate as validate_taskspec

        validate_taskspec(self.task, "task_spec")


@dataclass
class TaskCancel(_Message):
    ARTIFACT: ClassVar[str] = "task.cancel"
    _KNOWN: ClassVar[tuple[str, ...]] = ("task_id", "reason", "seq")

    task_id: str = ""
    reason: str = ""
    seq: int = 0
    schema_version: int = 1
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskCancel":
        return cls(
            task_id=data.get("task_id", ""),
            reason=data.get("reason", ""),
            seq=data.get("seq", 0),
            schema_version=data.get("schema_version", 1),
            extra=_split_extra(data, cls._KNOWN),
        )

    def to_dict(self) -> dict[str, Any]:
        out = {
            "schema_version": self.schema_version,
            "type": self.ARTIFACT,
            "task_id": self.task_id,
            "reason": self.reason,
            "seq": self.seq,
        }
        return {**_prune(out), **self.extra}


# --------------------------------------------------------------------------
# runner -> hub


@dataclass
class TaskProgress(_Message):
    ARTIFACT: ClassVar[str] = "task.progress"
    _KNOWN: ClassVar[tuple[str, ...]] = ("task_id", "seq", "kind", "payload", "attempt")

    task_id: str = ""
    seq: int = 0
    kind: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    #: G-4: the attempt that emitted this frame (0 = unset/legacy) — see
    #: :attr:`TaskAssign.attempt`.
    attempt: int = 0
    schema_version: int = 1
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskProgress":
        return cls(
            task_id=data.get("task_id", ""),
            seq=data.get("seq", 0),
            kind=data.get("kind", ""),
            payload=data.get("payload", {}) or {},
            attempt=data.get("attempt", 0),
            schema_version=data.get("schema_version", 1),
            extra=_split_extra(data, cls._KNOWN),
        )

    def to_dict(self) -> dict[str, Any]:
        out = {
            "schema_version": self.schema_version,
            "type": self.ARTIFACT,
            "task_id": self.task_id,
            "seq": self.seq,
            "kind": self.kind,
            "payload": self.payload,
            "attempt": self.attempt,
        }
        # payload is required by schema even when empty; keep it verbatim.
        pruned = _prune({k: v for k, v in out.items() if k != "payload"})
        return {**pruned, "payload": self.payload, **self.extra}

    def _validate_embedded(self) -> None:
        # A usage frame carries a strict five-component UsageSplit.
        if self.kind == "usage":
            from stapel_taskspecs import validate as validate_taskspec

            usage = self.payload.get("usage")
            validate_taskspec(usage, "usage_split")


@dataclass
class TaskReportMessage(_Message):
    ARTIFACT: ClassVar[str] = "task.report"
    _KNOWN: ClassVar[tuple[str, ...]] = ("task_id", "report", "seq", "attempt")

    task_id: str = ""
    report: dict[str, Any] = field(default_factory=dict)
    seq: int = 0
    #: G-4: the attempt that emitted this frame (0 = unset/legacy) — see
    #: :attr:`TaskAssign.attempt`.
    attempt: int = 0
    schema_version: int = 1
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskReportMessage":
        report = data.get("report", {}) or {}
        return cls(
            task_id=data.get("task_id") or report.get("task_id", ""),
            report=report,
            seq=data.get("seq", 0),
            attempt=data.get("attempt", 0),
            schema_version=data.get("schema_version", 1),
            extra=_split_extra(data, cls._KNOWN),
        )

    def to_dict(self) -> dict[str, Any]:
        out = {
            "schema_version": self.schema_version,
            "type": self.ARTIFACT,
            "task_id": self.task_id,
            "report": self.report,
            "seq": self.seq,
            "attempt": self.attempt,
        }
        return {**_prune(out), **self.extra}

    @property
    def report_model(self):
        """The embedded report as a :class:`stapel_taskspecs.TaskReport` model."""
        from stapel_taskspecs import TaskReport

        return TaskReport.from_dict(self.report)

    def _validate_embedded(self) -> None:
        from stapel_taskspecs import validate as validate_taskspec

        validate_taskspec(self.report, "task_report")


#: wire message ``type`` -> model class
MESSAGES: dict[str, type] = {
    Hello.ARTIFACT: Hello,
    TaskAssign.ARTIFACT: TaskAssign,
    TaskProgress.ARTIFACT: TaskProgress,
    TaskReportMessage.ARTIFACT: TaskReportMessage,
    TaskCancel.ARTIFACT: TaskCancel,
    Ping.ARTIFACT: Ping,
    Pong.ARTIFACT: Pong,
}
