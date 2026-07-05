"""Reference harness adapter: a JSONL stream to a child process.

This is the "opencode-class" escape hatch — an open-weight / bring-your-own
harness driven over a line-delimited JSON protocol on the child's stdin/stdout:

    parent -> child (stdin) : {"type": "turn", "prompt": "..."}
    child  -> parent(stdout): {"type": "progress", ...}      # zero or more
    child  -> parent(stdout): {"type": "result", "text": "...", "usage": {...}}

``usage`` on the result line is the canonical five-component split (see
:func:`stapel_runner_protocol.usage.usage_from_mapping`); swap ``usage_mapper``
for :func:`usage_from_anthropic` if your child emits provider-native counts.

The process is created through an injectable ``spawn`` callable, so the whole
adapter is testable against an in-memory fake child with no real subprocess.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any, Callable

from .adapters import HarnessAdapter, RoleSpec, Session, TurnResult
from .errors import AdapterError
from .usage import usage_from_mapping

__all__ = ["SubprocessAdapter", "SubprocessSession"]

#: A spawned child: needs text-mode stdin/stdout line I/O + terminate/wait.
SpawnFn = Callable[[RoleSpec], Any]


def _default_spawn(command: Any) -> SpawnFn:
    def spawn(role_spec: RoleSpec) -> Any:
        cmd = command(role_spec) if callable(command) else command
        if not cmd:
            raise AdapterError("SubprocessAdapter needs a non-empty command")
        env = None
        if role_spec.llm_base_url:
            import os

            env = {**os.environ, "ANTHROPIC_BASE_URL": role_spec.llm_base_url}
        return subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )

    return spawn


class SubprocessSession(Session):
    """One turn-per-request JSONL session over a child process."""

    def __init__(
        self,
        process: Any,
        *,
        usage_mapper: Callable[[Any], Any] = usage_from_mapping,
        on_progress: Callable[[dict], None] | None = None,
    ) -> None:
        self._proc = process
        self._usage_mapper = usage_mapper
        self._on_progress = on_progress
        self._closed = False

    def turn(self, prompt: str) -> TurnResult:
        if self._closed:
            raise AdapterError("turn() on a closed subprocess session")
        self._write({"type": "turn", "prompt": prompt})
        while True:
            line = self._proc.stdout.readline()
            if not line:
                raise AdapterError("child closed stdout before returning a result")
            message = json.loads(line)
            mtype = message.get("type")
            if mtype == "result":
                usage = self._usage_mapper(message.get("usage", {}))
                return TurnResult(text=message.get("text", ""), usage=usage, raw=message)
            if mtype == "error":
                raise AdapterError(f"child reported error: {message.get('message')}")
            # progress / anything else: surface and keep reading.
            if self._on_progress is not None:
                self._on_progress(message)

    def _write(self, obj: dict) -> None:
        self._proc.stdin.write(json.dumps(obj) + "\n")
        self._proc.stdin.flush()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        proc = self._proc
        try:
            if proc.stdin is not None:
                proc.stdin.close()
        except Exception:
            pass
        terminate = getattr(proc, "terminate", None)
        if terminate is not None and getattr(proc, "poll", lambda: 0)() is None:
            terminate()
        wait = getattr(proc, "wait", None)
        if wait is not None:
            try:
                wait(timeout=5)
            except Exception:
                pass


class SubprocessAdapter(HarnessAdapter):
    """Spawn a JSONL child per session.

    ``command`` is a list (``["my-harness", "--json"]``) or a callable
    ``role_spec -> list``. Inject ``spawn`` in tests to avoid a real process.
    """

    def __init__(
        self,
        command: Any = None,
        *,
        spawn: SpawnFn | None = None,
        usage_mapper: Callable[[Any], Any] = usage_from_mapping,
        on_progress: Callable[[dict], None] | None = None,
    ) -> None:
        self._spawn = spawn or _default_spawn(command)
        self._usage_mapper = usage_mapper
        self._on_progress = on_progress

    def open_session(self, role_spec: RoleSpec) -> SubprocessSession:
        process = self._spawn(role_spec)
        return SubprocessSession(
            process,
            usage_mapper=self._usage_mapper,
            on_progress=self._on_progress,
        )
