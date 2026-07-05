# Changelog

All notable changes to stapel-runner-protocol are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project uses pre-1.0 semver: **minor = breaking**, patch = compatible.

## [0.1.0] - 2026-07-06

Initial release. WS orchestrator<->runner protocol + harness-adapter ABC for
Stapel Studio (steel thread, SN-2).

### Added
- **Protocol messages** (`messages.py`) with JSON Schema v1 (`schemas/`,
  Draft 2020-12): `hello`, `task.assign`, `task.progress`, `task.report`,
  `task.cancel`, `ping`, `pong`. Every frame carries `schema_version: 1` and a
  `type` const, is forward-compatible (unknown top-level fields preserved in
  `.extra`), and has taskspecs-style `from_dict` / `to_dict` / `validate` /
  `parse`. Task and report payloads are **imported** from `stapel-taskspecs`
  (validated as embedded artifacts), never re-invented; a `task.progress` frame
  with `kind: "usage"` validates its embedded five-component `UsageSplit`.
- **Transport-agnostic core** (`transport.py`): `encode` / `decode` over JSON
  text frames, dispatching on the envelope `type`. Zero runtime deps beyond the
  stdlib + this package.
- **Sequencing state machine** (`state.py`): `OutboxLog` / `InboxTracker` /
  `TaskChannel` / `ConnectionState`. Progress is **idempotent by
  `(task_id, seq)`** (a runner may re-send from its last checkpoint — a git
  commit — after a reconnect); **resume** replays a hub's buffered commands after
  the per-task `last_seq` a runner declares in `hello.resume`.
- **Harness-adapter ABC** (`adapters.py`): `open_session(role_spec) -> Session`,
  `Session.turn(prompt) -> TurnResult`, `oneshot(role_spec, prompt)`, `close()`.
  `TurnResult` is `{text, usage}` with a strict, validated five-component
  `stapel_taskspecs.UsageSplit`.
- **Reference adapters**: `agent_sdk_adapter.py` (persistent claude-agent-sdk
  session; SDK is an optional extra — the driver and text/usage extraction are
  fully exercised on a fake async client) and `subprocess_adapter.py` (JSONL
  stream to a child process).
- **Optional websockets binding** (`transport_ws.py`, extra `[websockets]`):
  runner-side outbound `RunnerConnection` (bearer-token auth) + hub-side
  `iter_messages`. The protocol core needs none of it.
- **Usage mapping** (`usage.py`): `usage_from_anthropic` /
  `usage_from_mapping` onto the five-component split.
- Django-free, lazy (PEP 562) package import; `py.typed`.

### Notes
- Roles, progress kinds, capabilities and statuses are **open** strings, never
  closed enums. Anti-cheat rules, permission policies, concrete system prompts
  and routing config are **not** here and never will be (OSS/moat boundary,
  studio-design §2.1 / §6: "механизмы открыты, мозги закрыты").
- Transport decision (SN-2): a transport-agnostic core + a thin optional
  `websockets` wrapper, chosen over a hard `websockets` dependency to keep the
  OSS dependency surface minimal and the protocol logic testable without a
  network or an event loop.
