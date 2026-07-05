"""Sequencing state machine: idempotent progress + resume/replay on reconnect."""

from __future__ import annotations

import pytest

from stapel_runner_protocol import (
    ConnectionState,
    InboxTracker,
    OutboxLog,
    TaskCancel,
    TaskProgress,
)
from stapel_runner_protocol.errors import ProtocolStateError


def _progress(seq=None):
    return TaskProgress(task_id="T-001", seq=seq or 0, kind="state", payload={"n": seq})


# --- idempotency by (task_id, seq) --------------------------------------


def test_inbox_dedups_duplicate_seq():
    inbox = InboxTracker()
    assert inbox.receive(1) is True
    assert inbox.receive(1) is False  # duplicate -> idempotent skip
    assert inbox.last_seq == 1


def test_inbox_contiguous_high_water_mark():
    inbox = InboxTracker()
    inbox.receive(1)
    inbox.receive(3)  # gap
    assert inbox.last_seq == 1  # 2 is missing, so 3 doesn't advance the mark
    inbox.receive(2)
    assert inbox.last_seq == 3  # gap filled -> mark jumps


def test_connection_progress_idempotent():
    hub = ConnectionState(role="hub")
    p1 = TaskProgress(task_id="T-001", seq=1, kind="state", payload={})
    dup = TaskProgress(task_id="T-001", seq=1, kind="state", payload={})
    assert hub.receive(p1) is True
    assert hub.receive(dup) is False  # runner re-sent from its checkpoint; hub drops it


# --- outbox seq assignment + replay -------------------------------------


def test_outbox_assigns_monotonic_seq():
    outbox = OutboxLog()
    a, b, c = outbox.emit(_progress()), outbox.emit(_progress()), outbox.emit(_progress())
    assert [a.seq, b.seq, c.seq] == [1, 2, 3]
    assert outbox.last_seq == 3


def test_outbox_replay_since():
    outbox = OutboxLog()
    for _ in range(5):
        outbox.emit(_progress())
    tail = outbox.since(2)
    assert [m.seq for m in tail] == [3, 4, 5]


def test_outbox_ack_trims():
    outbox = OutboxLog()
    for _ in range(5):
        outbox.emit(_progress())
    outbox.ack(3)
    assert [m.seq for m in outbox.since(0)] == [4, 5]


# --- end-to-end resume/replay handshake ---------------------------------


def test_resume_replays_missing_hub_commands():
    # Hub emits three commands for a task; runner only received the first two
    # before the connection dropped.
    hub = ConnectionState(role="hub")
    runner = ConnectionState(role="runner")

    for reason in ("a", "b", "c"):
        cmd = hub.emit(TaskCancel(task_id="T-001", reason=reason))
        if reason in ("a", "b"):
            runner.receive(cmd)

    # Reconnect: runner declares what it has; hub replays the rest.
    resume = runner.resume_map()
    assert resume == {"T-001": 2}
    replay = hub.replay_for(resume)
    assert [m.seq for m in replay["T-001"]] == [3]
    assert replay["T-001"][0].reason == "c"


def test_resume_map_empty_on_fresh_connection():
    runner = ConnectionState(role="runner")
    assert runner.resume_map() == {}


def test_emit_rejects_unsequenced_message():
    hub = ConnectionState(role="hub")
    from stapel_runner_protocol import Ping

    with pytest.raises(ProtocolStateError):
        hub.emit(Ping(nonce=1))


def test_channel_requires_task_id():
    hub = ConnectionState(role="hub")
    with pytest.raises(ProtocolStateError):
        hub.emit(TaskProgress(task_id="", seq=0, kind="state", payload={}))
