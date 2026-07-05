"""Message models: round-trip, forward-compat extra, embedded-artifact validation."""

from __future__ import annotations

import pytest

from stapel_runner_protocol import (
    Hello,
    Ping,
    Pong,
    TaskAssign,
    TaskCancel,
    TaskProgress,
    TaskReportMessage,
    decode,
    encode,
)
from stapel_runner_protocol.errors import SchemaValidationError, UnknownMessageError
from stapel_runner_protocol.messages import MESSAGES


@pytest.mark.parametrize(
    "cls, fixture_name",
    [
        (Hello, "hello"),
        (TaskAssign, "task_assign"),
        (TaskProgress, "task_progress"),
        (TaskReportMessage, "task_report_message"),
        (TaskCancel, "task_cancel"),
    ],
)
def test_round_trip_preserves_payload(cls, fixture_name, request):
    data = request.getfixturevalue(fixture_name)
    obj = cls.parse(data)
    round_tripped = obj.to_dict()
    # to_dict re-validates cleanly and re-emits every original field.
    obj.validate()
    for key, value in data.items():
        assert round_tripped[key] == value


def test_control_frames_round_trip():
    ping = Ping.parse({"schema_version": 1, "type": "ping", "nonce": 7})
    assert ping.to_dict()["nonce"] == 7
    pong = Pong.answer(ping)
    pong.validate()
    assert pong.nonce == 7


def test_decode_dispatches_by_type(task_assign):
    frame = encode(TaskAssign.from_dict(task_assign))
    obj = decode(frame, validate=True)
    assert isinstance(obj, TaskAssign)
    assert obj.task_id == "T-001"
    assert obj.task_spec.id == "T-001"  # embedded taskspecs model


def test_decode_unknown_type_raises():
    with pytest.raises(UnknownMessageError):
        decode('{"schema_version":1,"type":"task.explode"}')


def test_forward_compat_unknown_field_survives_round_trip(hello):
    hello["future_flag"] = {"beta": True}
    obj = Hello.from_dict(hello)
    assert obj.extra == {"future_flag": {"beta": True}}
    assert obj.to_dict()["future_flag"] == {"beta": True}


def test_task_assign_validates_embedded_taskspec(task_assign):
    task_assign["task"]["id"] = ""  # break the embedded TaskSpec (minLength 1)
    with pytest.raises(SchemaValidationError):
        TaskAssign.parse(task_assign)


def test_task_report_validates_embedded_report(task_report_message):
    task_report_message["report"]["usage"].pop("thinking")  # partial usage split
    with pytest.raises(SchemaValidationError):
        TaskReportMessage.parse(task_report_message)


def test_report_model_exposes_taskspecs_model(task_report_message):
    msg = TaskReportMessage.parse(task_report_message)
    assert msg.report_model.status == "done"
    assert msg.report_model.usage.total_tokens == 18000 + 320 + 640


def test_messages_registry_covers_every_type():
    assert set(MESSAGES) == {
        "hello", "task.assign", "task.progress", "task.report", "task.cancel", "ping", "pong",
    }
