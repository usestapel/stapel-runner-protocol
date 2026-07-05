"""Subprocess JSONL adapter, driven against an in-memory fake child process."""

from __future__ import annotations

import io
import json

import pytest

from stapel_runner_protocol import SubprocessAdapter, RoleSpec
from stapel_runner_protocol.errors import AdapterError
from stapel_taskspecs import UsageSplit


class FakeChild:
    """A fake JSONL child: reads turn frames on stdin, scripts stdout replies."""

    def __init__(self, script):
        # script: prompt -> list[dict] lines to emit (terminated by a result).
        self._script = script
        self.stdin = io.StringIO()
        self.stdout = io.StringIO()
        self._read_pos = 0
        self.terminated = False

    # driven by the adapter writing a turn to stdin, then reading stdout:
    def feed_turn(self, prompt):
        for line in self._script(prompt):
            self.stdout.write(json.dumps(line) + "\n")
        self.stdout.seek(self._read_pos)

    def poll(self):
        return None if not self.terminated else 0

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0


class DriverChild(FakeChild):
    """Wire stdin writes to trigger stdout scripting (one turn at a time)."""

    def __init__(self, script):
        super().__init__(script)
        self.stdin = self._Stdin(self)

    class _Stdin:
        def __init__(self, child):
            self._child = child

        def write(self, data):
            for line in data.splitlines():
                if not line.strip():
                    continue
                msg = json.loads(line)
                if msg.get("type") == "turn":
                    self._child.feed_turn(msg["prompt"])

        def flush(self):
            pass

        def close(self):
            pass


def _result_script(prompt):
    return [
        {"type": "progress", "kind": "state", "payload": {"phase": "start"}},
        {
            "type": "result",
            "text": f"done:{prompt}",
            "usage": {"cache_read": 100, "cache_write": 0, "fresh_input": 8, "output": 20, "thinking": 0},
        },
    ]


def test_turn_reads_until_result_and_maps_usage():
    progresses = []
    adapter = SubprocessAdapter(
        spawn=lambda rs: DriverChild(_result_script),
        on_progress=progresses.append,
    )
    session = adapter.open_session(RoleSpec(backend="subprocess"))
    result = session.turn("build it")
    assert result.text == "done:build it"
    assert isinstance(result.usage, UsageSplit)
    assert result.usage.cache_read == 100 and result.usage.output == 20
    assert progresses and progresses[0]["kind"] == "state"


def test_error_line_raises():
    def err_script(prompt):
        return [{"type": "error", "message": "harness blew up"}]

    adapter = SubprocessAdapter(spawn=lambda rs: DriverChild(err_script))
    with pytest.raises(AdapterError):
        adapter.open_session(RoleSpec()).turn("x")


def test_closed_stdout_raises():
    def empty_script(prompt):
        return []

    adapter = SubprocessAdapter(spawn=lambda rs: DriverChild(empty_script))
    with pytest.raises(AdapterError):
        adapter.open_session(RoleSpec()).turn("x")


def test_close_terminates_child():
    child = DriverChild(_result_script)
    adapter = SubprocessAdapter(spawn=lambda rs: child)
    session = adapter.open_session(RoleSpec())
    session.turn("a")
    session.close()
    assert child.terminated is True
    session.close()  # idempotent


def test_oneshot_maps_usage_and_closes():
    child = DriverChild(_result_script)
    adapter = SubprocessAdapter(spawn=lambda rs: child)
    result = adapter.oneshot(RoleSpec(), "quick")
    assert result.text == "done:quick"
    assert child.terminated is True


def test_default_spawn_requires_command():
    adapter = SubprocessAdapter(command=None)
    with pytest.raises(AdapterError):
        adapter.open_session(RoleSpec())
