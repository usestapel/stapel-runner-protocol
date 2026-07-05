"""Sequencing, idempotency and resume/replay — the protocol state machine.

Two per-task streams flow over one connection, each numbered independently:

* **runner -> hub progress** (``task.progress`` / ``task.report``). The hub is
  the durable side; it applies each ``(task_id, seq)`` **exactly once**, so a
  runner may safely re-send from its last checkpoint (a git commit) after a
  reconnect — duplicates are dropped.
* **hub -> runner commands** (``task.assign`` / ``task.cancel``). The hub buffers
  its outbound frames; on reconnect the runner declares, per task, the last seq
  it contiguously received (``hello.resume``), and the hub **replays** everything
  after it.

The pieces here are transport-agnostic and synchronous — the whole resume dance
is exercisable in-memory. ``checkpoint = git commit`` is the durability semantics
the hub relies on: the runner's re-send after a drop resumes from the commit it
last recorded, and idempotency makes the overlap harmless.
"""

from __future__ import annotations

from typing import Any

from .errors import ProtocolStateError

#: message types that participate in per-task sequencing.
SEQUENCED_TYPES = frozenset({"task.assign", "task.cancel", "task.progress", "task.report"})


def is_sequenced(message: Any) -> bool:
    """True if ``message`` belongs to a per-task sequence (has task_id + seq)."""
    return getattr(message, "ARTIFACT", None) in SEQUENCED_TYPES


class OutboxLog:
    """A sender's buffer of seq'd frames for one task, supporting replay."""

    def __init__(self) -> None:
        self._buffer: list[Any] = []
        self._next: int = 1

    def emit(self, message: Any) -> Any:
        """Assign the next seq to ``message``, buffer it, and return it."""
        message.seq = self._next
        self._next += 1
        self._buffer.append(message)
        return message

    def since(self, last_seq: int) -> list[Any]:
        """Buffered frames with ``seq > last_seq`` (the replay tail)."""
        return [m for m in self._buffer if m.seq > last_seq]

    def ack(self, seq: int) -> None:
        """Drop buffered frames the peer has confirmed (``seq <=`` given)."""
        self._buffer = [m for m in self._buffer if m.seq > seq]

    @property
    def last_seq(self) -> int:
        """Highest seq assigned so far (0 before anything is emitted)."""
        return self._next - 1


class InboxTracker:
    """A receiver's idempotency ledger for one task's inbound seqs."""

    def __init__(self) -> None:
        self._seen: set[int] = set()
        self._contiguous: int = 0

    def receive(self, seq: int) -> bool:
        """Record ``seq``; return True if new, False if a duplicate (idempotent).

        The contiguous high-water mark (:attr:`last_seq`) only advances across
        a gap once the missing seqs arrive.
        """
        if seq in self._seen:
            return False
        self._seen.add(seq)
        while (self._contiguous + 1) in self._seen:
            self._contiguous += 1
        return True

    @property
    def last_seq(self) -> int:
        """Highest seq such that every seq in ``1..last_seq`` has been received."""
        return self._contiguous


class TaskChannel:
    """Outbound + inbound sequencing for a single task on one connection."""

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        self.outbox = OutboxLog()
        self.inbox = InboxTracker()

    def emit(self, message: Any) -> Any:
        """Stamp ``message`` with the next outbound seq and buffer it."""
        return self.outbox.emit(message)

    def receive(self, message: Any) -> bool:
        """Register an inbound ``message``; return False if a duplicate seq."""
        return self.inbox.receive(message.seq)

    @property
    def last_received(self) -> int:
        """Last contiguously-received inbound seq (for the resume declaration)."""
        return self.inbox.last_seq

    def replay(self, peer_last_seq: int) -> list[Any]:
        """Outbound frames the peer is missing (``seq > peer_last_seq``)."""
        return self.outbox.since(peer_last_seq)


class ConnectionState:
    """Per-connection sequencing across all of its tasks.

    One instance lives on each side of a connection. Both sides use the same
    object; ``role`` is informational (``"runner"`` or ``"hub"``).
    """

    def __init__(self, role: str = "") -> None:
        self.role = role
        self.channels: dict[str, TaskChannel] = {}

    def channel(self, task_id: str) -> TaskChannel:
        """Return (creating on first use) the channel for ``task_id``."""
        if not task_id:
            raise ProtocolStateError("a sequenced message must carry a task_id")
        return self.channels.setdefault(task_id, TaskChannel(task_id))

    def emit(self, message: Any) -> Any:
        """Assign the next outbound seq to a sequenced ``message``."""
        if not is_sequenced(message):
            raise ProtocolStateError(
                f"{getattr(message, 'ARTIFACT', type(message).__name__)} is not a sequenced message"
            )
        return self.channel(message.task_id).emit(message)

    def receive(self, message: Any) -> bool:
        """Register an inbound sequenced ``message``; False on duplicate seq."""
        if not is_sequenced(message):
            raise ProtocolStateError(
                f"{getattr(message, 'ARTIFACT', type(message).__name__)} is not a sequenced message"
            )
        return self.channel(message.task_id).receive(message)

    def resume_map(self) -> dict[str, int]:
        """Per-task last-received seqs to advertise in ``hello.resume``.

        Only tasks with at least one received frame are included.
        """
        return {tid: ch.last_received for tid, ch in self.channels.items() if ch.last_received}

    def replay_for(self, resume_map: dict[str, int]) -> dict[str, list[Any]]:
        """Given a peer's ``resume`` map, the frames to re-send per task."""
        return {tid: self.channel(tid).replay(int(last)) for tid, last in (resume_map or {}).items()}
