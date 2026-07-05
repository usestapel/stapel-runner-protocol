"""Transport-agnostic protocol core: encode / decode.

The wire is JSON text frames. This module turns message dataclasses into frames
and back, dispatching on the envelope ``type``. It has **zero** runtime
dependencies beyond the stdlib and this package — the websockets binding
(:mod:`stapel_runner_protocol.transport_ws`) is a thin optional wrapper on top,
so the whole protocol (encode/decode + the :mod:`state` machine) is testable
without a network or an event loop.

Rationale for the split (SN-2): a transport-agnostic core keeps the OSS
dependency surface minimal — ``websockets`` is an extra, not a hard dep — and
lets a host bring its own transport (raw asyncio, aiohttp, an in-process queue
for tests) around the same encode/decode/state-machine kernel.
"""

from __future__ import annotations

import json
from typing import Any

from .errors import RunnerProtocolError, UnknownMessageError
from .messages import MESSAGES


def encode(message: Any) -> str:
    """Serialize a message dataclass (or a plain dict) to a JSON text frame."""
    data = message.to_dict() if hasattr(message, "to_dict") else message
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


def to_frame(message: Any) -> str:
    """Alias for :func:`encode` (frame = one JSON text message)."""
    return encode(message)


def decode(frame: str | bytes | dict, *, validate: bool = False):
    """Parse a JSON frame into the matching message dataclass.

    ``frame`` may be a JSON string/bytes or an already-parsed dict. The envelope
    ``type`` selects the model; an unknown type raises
    :class:`~stapel_runner_protocol.errors.UnknownMessageError`. Pass
    ``validate=True`` to schema-validate the message (and any embedded taskspecs
    artifact) before returning it.
    """
    if isinstance(frame, (str, bytes, bytearray)):
        try:
            data = json.loads(frame)
        except (ValueError, TypeError) as exc:
            raise RunnerProtocolError(f"frame is not valid JSON: {exc}") from exc
    else:
        data = frame
    if not isinstance(data, dict):
        raise RunnerProtocolError(f"frame must decode to an object, got {type(data).__name__}")

    mtype = data.get("type")
    model = MESSAGES.get(mtype)
    if model is None:
        raise UnknownMessageError(
            f"unknown message type {mtype!r}; known: {sorted(MESSAGES)}"
        )
    return model.parse(data, validate=validate)
