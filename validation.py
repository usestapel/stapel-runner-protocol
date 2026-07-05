"""JSON Schema loading and validation for the runner-protocol messages.

The schemas ship as package data under ``schemas/``. This module loads them
once and exposes a single :func:`validate` entry point plus the message-name
registry, mirroring the shape of :mod:`stapel_taskspecs.validation`.

Embedded artifacts (the ``task`` on ``task.assign``, the ``report`` on
``task.report``, the ``usage`` inside a ``task.progress`` payload) are *not*
re-specified here — they are validated against the stapel-taskspecs schemas by
the message models. This keeps the protocol schemas self-contained and free of
cross-package ``$ref``.

``jsonschema`` is imported here and only here, so ``import
stapel_runner_protocol`` stays dependency-light until a symbol is touched.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .errors import SchemaValidationError, UnknownMessageError

_SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"

#: wire message ``type`` -> schema filename. The canonical list of v1 messages.
SCHEMA_FILES: dict[str, str] = {
    "hello": "hello.v1.json",
    "task.assign": "task_assign.v1.json",
    "task.progress": "task_progress.v1.json",
    "task.report": "task_report.v1.json",
    "task.cancel": "task_cancel.v1.json",
    "ping": "ping.v1.json",
    "pong": "pong.v1.json",
}

#: current schema major version stamped into every message.
SCHEMA_VERSION = 1

#: current wire protocol major version (carried in ``hello.protocol_version``).
PROTOCOL_VERSION = 1


def message_types() -> list[str]:
    """Names of every message type that has a registered schema."""
    return list(SCHEMA_FILES)


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict[str, Any]:
    """Return the parsed JSON Schema for message ``name`` (cached)."""
    try:
        filename = SCHEMA_FILES[name]
    except KeyError:
        raise UnknownMessageError(
            f"unknown message type {name!r}; known: {sorted(SCHEMA_FILES)}"
        ) from None
    return json.loads((_SCHEMA_DIR / filename).read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def _validator(name: str):
    from jsonschema import Draft202012Validator

    return Draft202012Validator(load_schema(name))


def iter_errors(instance: Any, name: str) -> list[str]:
    """Return a sorted list of human-readable validation error lines.

    Empty list means the instance is valid. Does not raise on invalidity —
    use :func:`validate` for the raising variant.
    """
    validator = _validator(name)
    lines = []
    for err in sorted(validator.iter_errors(instance), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "<root>"
        lines.append(f"{loc}: {err.message}")
    return lines


def is_valid(instance: Any, name: str) -> bool:
    """True if ``instance`` validates against the ``name`` message schema."""
    return not iter_errors(instance, name)


def validate(instance: Any, name: str) -> None:
    """Validate ``instance`` against the ``name`` message schema.

    Raises :class:`~stapel_runner_protocol.errors.SchemaValidationError` with
    the collected error lines on any failure; returns ``None`` on success.
    """
    errors = iter_errors(instance, name)
    if errors:
        raise SchemaValidationError(
            f"{name} failed schema validation ({len(errors)} error(s))",
            errors=errors,
        )
