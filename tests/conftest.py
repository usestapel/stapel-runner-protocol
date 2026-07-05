"""Shared sample fixtures for the runner-protocol messages.

Samples mirror the *structure* of real slice frames — enough to exercise the
schemas and the state machine — without carrying any pipeline rules/prose.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def usage_split() -> dict:
    return {
        "cache_read": 18000,
        "cache_write": 0,
        "fresh_input": 320,
        "output": 640,
        "thinking": 0,
    }


@pytest.fixture
def task_spec() -> dict:
    return {
        "schema_version": 1,
        "id": "T-001",
        "type": "feature",
        "goal": "CRUD entity: list, create, view and edit",
        "status": "QUEUED",
        "risk": ["validation"],
        "criteria": [{"id": "C1", "text": "Given empty db; When POST; Then 201"}],
        "budget": {"iterations": 3, "tokens_m": 1, "wall_min": 20},
    }


@pytest.fixture
def task_report(usage_split) -> dict:
    return {
        "schema_version": 1,
        "task_id": "T-001",
        "status": "done",
        "summary_business": "Entity CRUD is live.",
        "files_changed": ["apps/x/models.py"],
        "controls": {"tests": {"status": "pass", "log": "12 passed"}},
        "commits": ["abc1234"],
        "iterations": 2,
        "usage": usage_split,
    }


@pytest.fixture
def hello() -> dict:
    return {
        "schema_version": 1,
        "type": "hello",
        "protocol_version": 1,
        "project_id": "brave-falcon-1042",
        "runner_version": "0.1.0",
        "capabilities": ["agent-sdk", "subprocess"],
    }


@pytest.fixture
def task_assign(task_spec) -> dict:
    return {
        "schema_version": 1,
        "type": "task.assign",
        "task_id": "T-001",
        "task": task_spec,
        "role": "coder",
        "invocation": {
            "backend": "agent-sdk",
            "model": "claude-opus-4-8",
            "session": "per-task",
            "system_prompt_ref": "prompts/coder@3",
            "allowed_tools": ["bash", "edit"],
            "llm_base_url": "http://llm-proxy.internal",
            "budget": {"max_turns": 8},
        },
        "seq": 1,
    }


@pytest.fixture
def task_progress(usage_split) -> dict:
    return {
        "schema_version": 1,
        "type": "task.progress",
        "task_id": "T-001",
        "seq": 1,
        "kind": "usage",
        "payload": {"usage": usage_split},
    }


@pytest.fixture
def task_report_message(task_report) -> dict:
    return {
        "schema_version": 1,
        "type": "task.report",
        "task_id": "T-001",
        "report": task_report,
        "seq": 7,
    }


@pytest.fixture
def task_cancel() -> dict:
    return {
        "schema_version": 1,
        "type": "task.cancel",
        "task_id": "T-001",
        "reason": "superseded by T-002",
        "seq": 2,
    }
