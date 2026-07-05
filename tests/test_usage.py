"""Usage is always the strict five-component split, and is validated."""

from __future__ import annotations

import pytest

from stapel_runner_protocol import TaskProgress, usage_from_anthropic, usage_from_mapping
from stapel_runner_protocol.errors import SchemaValidationError
from stapel_taskspecs import UsageSplit


def test_anthropic_mapping_covers_five_components():
    anthropic = {
        "cache_read_input_tokens": 1000,
        "cache_creation_input_tokens": 200,
        "input_tokens": 50,
        "output_tokens": 300,
    }
    split = usage_from_anthropic(anthropic, thinking=40)
    assert isinstance(split, UsageSplit)
    assert split.to_dict() == {
        "cache_read": 1000,
        "cache_write": 200,
        "fresh_input": 50,
        "output": 300,
        "thinking": 40,
    }


def test_anthropic_mapping_defaults_thinking_zero():
    split = usage_from_anthropic({"output_tokens": 10})
    assert split.thinking == 0
    assert split.output == 10


def test_anthropic_mapping_reads_object_attrs():
    class U:
        cache_read_input_tokens = 5
        cache_creation_input_tokens = 0
        input_tokens = 2
        output_tokens = 3

    assert usage_from_anthropic(U()).prompt_tokens == 7


def test_mapping_helper_validates():
    split = usage_from_mapping({"cache_read": 1, "output": 2})
    assert split.cache_read == 1 and split.output == 2


def test_progress_usage_frame_validates_split(task_progress):
    TaskProgress.parse(task_progress)  # valid five-component usage


def test_progress_usage_frame_rejects_partial_split(task_progress):
    task_progress["payload"]["usage"].pop("thinking")
    with pytest.raises(SchemaValidationError):
        TaskProgress.parse(task_progress)


def test_progress_usage_frame_rejects_sixth_component(task_progress):
    task_progress["payload"]["usage"]["reasoning"] = 5  # closed object
    with pytest.raises(SchemaValidationError):
        TaskProgress.parse(task_progress)
