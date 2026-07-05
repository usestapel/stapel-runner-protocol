# stapel-runner-protocol — MODULE.md

Agent-facing map of this library: what it provides, its extension points, and
anti-patterns. Use it to classify a desired change as **app-layer usage** vs
**upstream contribution**. This is an **L1 library** (per
`docs/library-standard.md`): importable by anyone, Django-free, with no comm
surface, no settings namespace, no migrations, no service identity. It carries
the *structure* and the *sequencing discipline* of the orchestrator↔runner seam
— the OSS half of the boundary (studio-design §2.1 / §6: "механизмы открыты,
мозги закрыты").

- Package: `stapel-runner-protocol` (PyPI), Python package
  `stapel_runner_protocol`.
- Runtime deps: `stapel-taskspecs` and `jsonschema`. Optional extras:
  `websockets` (the WS binding), `agent-sdk` (the claude-agent-sdk adapter).
  No `stapel-core`, no Django.
- Consumers: the private studio-orchestrator (hub side) and studio-runner
  (in-container), plus any OSS consumer that speaks the pipeline wire format or
  contributes a harness backend.

## What this library provides

| Area | Contents |
|---|---|
| Messages (`messages.py`) | Dataclasses `Hello`, `TaskAssign`, `TaskProgress`, `TaskReportMessage`, `TaskCancel`, `Ping`, `Pong`. Each has tolerant `from_dict` (unknown keys → `.extra`), `to_dict`, `validate()`, `parse()`. `MESSAGES` maps wire `type` → class. `TaskAssign`/`TaskReportMessage` embed a stapel-taskspecs `TaskSpec`/`TaskReport` and validate it as part of `validate()`. |
| Schemas (`schemas/`) | Draft 2020-12 JSON Schema v1 for each message. Every envelope has `schema_version: const 1` + a `type: const`, accepts unknown top-level fields (forward-compat). Embedded task/report/usage artifacts are **not** re-specified — they are validated against the taskspecs schemas by the models. |
| Transport core (`transport.py`) | `encode` / `decode` / `to_frame` over JSON text frames, dispatching on the envelope `type`. Transport-agnostic; zero deps beyond stdlib + this package. |
| State machine (`state.py`) | `OutboxLog`, `InboxTracker`, `TaskChannel`, `ConnectionState`. Idempotency by `(task_id, seq)`; resume/replay via `resume_map()` / `replay_for()`. `is_sequenced()`. |
| Adapter ABC (`adapters.py`) | `HarnessAdapter` (`open_session` / `oneshot` / `close`), `Session` (`turn` / `close`), `RoleSpec` (built from a `task.assign` invocation), `TurnResult` (`{text, usage}`, usage is a validated five-component `UsageSplit`). |
| Reference adapters | `AgentSdkAdapter` / `AgentSdkSession` (`agent_sdk_adapter.py`, persistent SDK session), `SubprocessAdapter` / `SubprocessSession` (`subprocess_adapter.py`, JSONL child). |
| WS binding (`transport_ws.py`) | `RunnerConnection` (runner-side outbound, bearer token), `iter_messages` / `send` / `recv` (hub side). Optional extra. |
| Usage (`usage.py`) | `usage_from_anthropic`, `usage_from_mapping` → `stapel_taskspecs.UsageSplit`. |
| Validation (`validation.py`) | `validate` / `is_valid` / `iter_errors`, `load_schema`, `message_types`, `SCHEMA_FILES`, `SCHEMA_VERSION`, `PROTOCOL_VERSION`. Only this module imports `jsonschema`. |
| Errors (`errors.py`) | `RunnerProtocolError` base; `SchemaValidationError`, `UnknownMessageError`, `ProtocolStateError`, `AdapterError`, `AdapterUnavailableError`. |
| Public API (`__init__.py`, PEP 562 lazy) | The names above, re-exported lazily so `import stapel_runner_protocol` stays stdlib-only until a symbol is touched. |

## Extension points

The main seam is the **harness adapter ABC** — the contract a host implements to
add a model↔harness backend. Beyond it, the extension model is the schema shape
itself and injectable transport/spawn seams.

1. **`HarnessAdapter` / `Session` (provider ABC).** Subclass `HarnessAdapter`
   and implement `open_session(role_spec) -> Session`; subclass `Session` and
   implement `turn(prompt) -> TurnResult` + `close()`. `oneshot` and the
   `Session` context-manager come for free. This is how the community brings
   new backends (bring-your-own-harness). Contract: `TurnResult.usage` **must**
   be a five-component `UsageSplit` (validated on construction).
2. **Injectable transport / spawn seams.** `SubprocessAdapter(spawn=...)` and
   `AgentSdkAdapter(client_factory=...)` take injectable factories so a host can
   drive a custom process/client (and tests can use fakes) without subclassing.
   The transport core is transport-agnostic: bring any framing (raw asyncio,
   aiohttp, an in-process queue) around `encode`/`decode`/`ConnectionState`.
3. **Open value sets.** `role`, progress `kind`, `capabilities[]`, `status`,
   `invocation` fields and cancel `reason` are open strings, not `enum`
   constraints — a host adds its own without changing this library. Closed enums
   here would encode private routing policy into an OSS schema.
4. **Forward compatibility.** Message envelopes accept unknown top-level fields;
   models preserve them in `.extra` and re-emit on `to_dict`. A newer producer
   can add fields a v1 reader carries through untouched.
5. **Schema / protocol evolution** (pre-1.0: minor = breaking):
   - Additive, optional field → patch, same `schema_version` / `protocol_version`.
   - New required field, removed/renamed field, tightened constraint, or a change
     to the sequencing/resume semantics → new schema major (`*.v2.json`,
     `schema_version: 2`) + bumped `PROTOCOL_VERSION`, v1 kept for a deprecation
     window. Never mutate a shipped v1 schema in a breaking way.

## Anti-patterns

- **Do not re-define the task/report schema here.** `task.assign.task` and
  `task.report.report` are stapel-taskspecs artifacts, validated by that library.
  Re-specifying them would fork the contract (studio-design I7: boundaries =
  schemas).
- **Do not encode gate or routing logic in the protocol.** Anti-cheat rules,
  permission policies, concrete system prompts, model↔harness routing, and
  escalation thresholds are the private orchestrator's job. The protocol carries
  a `system_prompt_ref` (a pointer), never the prompt text; a `capabilities[]`
  list, never the routing table.
- **Do not collapse or omit the usage split.** Every `TurnResult` and every
  `kind: "usage"` progress frame reports all five components (zeros are fine). A
  partial split silently understates reasoning-class cost.
- **Do not add closed enums for policy values.** Hardcoding the role set, the
  capability list, or the FSM status set into an OSS schema leaks moat policy and
  breaks hosts with different value sets. Keep them open with examples.
- **Do not make the transport core depend on `websockets`.** The WS wrapper is a
  thin optional extra on purpose; the protocol logic must stay testable without a
  network or an event loop.
- **Do not treat this library as an authorization boundary.** It validates the
  *shape* of frames; whether an action is *allowed* is enforced in the private
  orchestrator (all container-originated content is untrusted, S5).

## App-layer usage vs upstream contribution

Litmus: *does the change alter the wire shape of a message, or the sequencing
contract, that every hub and runner sees?*

- **App-layer (no contribution):** implement your own `HarnessAdapter`/`Session`;
  inject a custom `spawn`/`client_factory`; attach host-specific data via unknown
  message fields (preserved in `.extra`); use your own `role`/`kind`/`capabilities`
  values; wrap models in your own domain types. None of this touches this library.
- **Upstream (contribute here):** a genuinely new shared message field, a new
  message type in the protocol, a new adapter capability every backend needs, a
  fix to a schema/model/state-machine bug, or a broadly useful reference adapter.
  Additive → patch; breaking → a new schema major + `protocol_version` bump per
  the evolution policy.
