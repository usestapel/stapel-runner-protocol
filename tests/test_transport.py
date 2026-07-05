"""Transport core round-trips; the websockets binding is import-guarded."""

from __future__ import annotations

import asyncio

import pytest

from stapel_runner_protocol import Hello, Ping, decode, encode
from stapel_runner_protocol.errors import AdapterUnavailableError, RunnerProtocolError


def test_encode_decode_round_trip(hello):
    obj = Hello.from_dict(hello)
    frame = encode(obj)
    assert isinstance(frame, str)
    back = decode(frame)
    assert isinstance(back, Hello)
    assert back.project_id == "brave-falcon-1042"


def test_decode_accepts_dict_and_bytes():
    frame = encode(Ping(nonce=1))
    assert isinstance(decode(frame.encode()), Ping)
    assert isinstance(decode({"schema_version": 1, "type": "ping", "nonce": 1}), Ping)


def test_decode_rejects_non_json():
    with pytest.raises(RunnerProtocolError):
        decode("{not json")


def test_decode_rejects_non_object():
    with pytest.raises(RunnerProtocolError):
        decode("[1, 2, 3]")


def test_decode_validate_flag_checks_schema():
    from stapel_runner_protocol.errors import SchemaValidationError

    with pytest.raises(SchemaValidationError):
        decode({"schema_version": 1, "type": "hello"}, validate=True)  # missing project_id


def test_ws_binding_is_import_guarded_without_websockets():
    # websockets is an optional extra; the module imports, but touching the
    # transport raises a clear, honest error when the dep is absent.
    from stapel_runner_protocol import transport_ws

    conn = transport_ws.RunnerConnection("ws://hub/runner", auth_token="tok")  # no import needed
    try:
        import websockets  # noqa: F401

        has_ws = True
    except ImportError:
        has_ws = False

    if not has_ws:
        with pytest.raises(AdapterUnavailableError):
            asyncio.run(conn.connect())
