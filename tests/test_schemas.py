"""JSON Schema surface: every schema is well-formed, samples validate,
invalid instances are rejected, and forward-compat holds."""

from __future__ import annotations

import pytest
from jsonschema import Draft202012Validator

from stapel_runner_protocol import validation
from stapel_runner_protocol.errors import SchemaValidationError, UnknownMessageError

MESSAGE_TYPES = ["hello", "task.assign", "task.progress", "task.report", "task.cancel", "ping", "pong"]


def test_all_message_types_registered():
    assert set(validation.message_types()) == set(MESSAGE_TYPES)


@pytest.mark.parametrize("name", MESSAGE_TYPES)
def test_schema_is_well_formed(name):
    schema = validation.load_schema(name)
    Draft202012Validator.check_schema(schema)
    assert schema["$id"].endswith(f"{name.replace('.', '_')}.v1.json")


def test_valid_samples_pass(hello, task_assign, task_progress, task_report_message, task_cancel):
    validation.validate(hello, "hello")
    validation.validate(task_assign, "task.assign")
    validation.validate(task_progress, "task.progress")
    validation.validate(task_report_message, "task.report")
    validation.validate(task_cancel, "task.cancel")
    validation.validate({"schema_version": 1, "type": "ping", "nonce": "n1"}, "ping")
    validation.validate({"schema_version": 1, "type": "pong", "nonce": "n1"}, "pong")


def test_missing_required_field_rejected(hello):
    hello.pop("project_id")
    assert not validation.is_valid(hello, "hello")


def test_schema_version_const_enforced(task_assign):
    task_assign["schema_version"] = 2
    assert not validation.is_valid(task_assign, "task.assign")


def test_type_const_enforced(task_progress):
    task_progress["type"] = "task.assign"
    assert not validation.is_valid(task_progress, "task.progress")


def test_forward_compat_unknown_top_level_field_ok(hello):
    hello["some_future_field"] = {"a": 1}
    validation.validate(hello, "hello")  # must not reject


def test_validate_raises_with_error_lines():
    with pytest.raises(SchemaValidationError) as exc:
        validation.validate({"schema_version": 1, "type": "task.cancel"}, "task.cancel")
    assert exc.value.errors


def test_unknown_message_type():
    with pytest.raises(UnknownMessageError):
        validation.load_schema("nope")
