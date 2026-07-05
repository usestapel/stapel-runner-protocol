"""Thin ``websockets`` binding over the transport-agnostic core.

Optional: ``pip install stapel-runner-protocol[websockets]``. The protocol
itself (encode/decode + :mod:`state`) needs none of this — this module only
wires frames onto a WebSocket. It is deliberately minimal; the interesting logic
(sequencing, idempotency, resume) lives in :mod:`state` and is transport-free.

Two ends:

* runner side — :class:`RunnerConnection`: the container holds the **outbound**
  connection (studio-design S3, no inbound ports). Connects with a project-scoped
  bearer token, sends/receives typed messages, answers pings.
* hub side — :func:`iter_messages`: decode frames off an accepted server-side
  socket.

``websockets`` is imported lazily; importing this module without it is fine, but
constructing a connection raises :class:`AdapterUnavailableError`.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from .errors import AdapterUnavailableError
from .messages import Ping, Pong
from .transport import decode, encode

__all__ = ["RunnerConnection", "iter_messages", "send", "recv"]


def _require_websockets():
    try:
        import websockets  # noqa: F401
    except ImportError as exc:  # pragma: no cover - exercised only without websockets
        raise AdapterUnavailableError(
            "websockets is not installed; `pip install stapel-runner-protocol[websockets]`"
        ) from exc
    return websockets


async def send(websocket: Any, message: Any) -> None:
    """Encode and send one message frame over ``websocket``."""
    await websocket.send(encode(message))


async def recv(websocket: Any, *, validate: bool = False):
    """Receive and decode one message frame from ``websocket``."""
    return decode(await websocket.recv(), validate=validate)


async def iter_messages(websocket: Any, *, validate: bool = False) -> AsyncIterator[Any]:
    """Yield decoded messages off a hub-side (server) socket until it closes."""
    async for frame in websocket:
        yield decode(frame, validate=validate)


class RunnerConnection:
    """Runner-side outbound WebSocket connection to the hub.

    ``auth_token`` is the project-scoped short-lived token issued when the
    container starts. Use as an async context manager::

        async with RunnerConnection(url, auth_token=tok) as conn:
            await conn.send(hello)
            async for msg in conn:
                ...
    """

    def __init__(self, url: str, *, auth_token: str | None = None, validate: bool = False, **connect_kwargs: Any) -> None:
        self._url = url
        self._validate = validate
        self._connect_kwargs = connect_kwargs
        if auth_token:
            headers = dict(connect_kwargs.pop("additional_headers", {}) or {})
            headers["Authorization"] = f"Bearer {auth_token}"
            self._connect_kwargs["additional_headers"] = headers
        self._ws: Any = None

    async def connect(self) -> "RunnerConnection":
        websockets = _require_websockets()
        self._ws = await websockets.connect(self._url, **self._connect_kwargs)
        return self

    async def send(self, message: Any) -> None:
        await send(self._ws, message)

    async def recv(self) -> Any:
        return await recv(self._ws, validate=self._validate)

    async def answer_ping(self, ping: Ping) -> None:
        """Reply to a received :class:`Ping` with the matching :class:`Pong`."""
        await self.send(Pong.answer(ping))

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def __aenter__(self) -> "RunnerConnection":
        return await self.connect()

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    def __aiter__(self) -> AsyncIterator[Any]:
        return iter_messages(self._ws, validate=self._validate)
