"""Exception types for stapel-runner-protocol.

Django-free, stdlib-only. Kept in their own module so callers can catch the
package's error taxonomy without importing ``jsonschema`` or ``websockets``.
"""

from __future__ import annotations


class RunnerProtocolError(Exception):
    """Base class for every error raised by stapel-runner-protocol."""


class SchemaValidationError(RunnerProtocolError):
    """A protocol message did not validate against its JSON Schema.

    ``errors`` holds one human-readable line per validation failure.
    """

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors: list[str] = errors or []


class UnknownMessageError(RunnerProtocolError):
    """No message type is registered under the requested wire ``type``."""


class ProtocolStateError(RunnerProtocolError):
    """A sequence/resume invariant was violated (e.g. a seq went backwards)."""


class AdapterError(RunnerProtocolError):
    """A harness adapter could not open a session or complete a turn.

    ``AdapterUnavailableError`` is the common subtype for a missing optional
    backend dependency (raised lazily, never at import time).
    """


class AdapterUnavailableError(AdapterError):
    """A reference adapter's optional backend dependency is not installed."""
