# stapel-runner-protocol

The wire protocol between the Stapel Studio **orchestrator (hub)** and the
in-container **runner**, plus the **harness-adapter** seam the runner uses to
drive a concrete model↔harness backend. This is the OSS half of the seam
(studio-design §2.1): the community brings harness backends; the brains
(anti-cheat, permissions, prompts, routing) stay private.

A small, **Django-free, pure-Python** library. Two halves:

1. **Protocol** — versioned JSON messages, a transport-agnostic encode/decode
   core, an optional `websockets` binding, and a sequencing state machine
   (idempotent progress, resume/replay on reconnect). Task and report *schemas*
   are imported from [`stapel-taskspecs`](https://stapel.dev), not re-invented.
2. **Harness adapters** — an ABC plus reference adapters for claude-agent-sdk
   (persistent session) and a subprocess JSONL harness.

## Install

```sh
pip install stapel-runner-protocol
# optional extras:
pip install "stapel-runner-protocol[websockets]"   # the WS transport binding
pip install "stapel-runner-protocol[agent-sdk]"    # the claude-agent-sdk adapter
```

Runtime deps are just `stapel-taskspecs` and `jsonschema`. Import is lazy
(PEP 562): `import stapel_runner_protocol` pulls in nothing heavy until you
touch a symbol.

## The protocol (studio-design §2.1)

The connection is always **outbound from the runner** (the project container
holds no inbound management ports, S3), authorized by a project-scoped
short-lived token.

```
runner → hub:   hello {protocol_version, project_id, runner_version, capabilities[], resume{}}
hub → runner:   task.assign {task: TaskSpec, role, invocation{backend, model, session,
                             system_prompt_ref, allowed_tools[], llm_base_url, budget}, seq}
runner → hub:   task.progress {task_id, seq, kind: state|tool|controls|usage, payload}
runner → hub:   task.report {report: TaskReport, seq}         # status done|blocked|failed
hub → runner:   task.cancel {task_id, reason, seq}            # graceful, at an automaton boundary
both:           ping / pong
resume:         after a reconnect the runner declares last_seq per task in `hello.resume`;
                the hub re-sends / replays anything after it (checkpoint = git commit)
```

| Message | Schema | Model |
|---|---|---|
| hello | `schemas/hello.v1.json` | `Hello` |
| task.assign | `schemas/task_assign.v1.json` | `TaskAssign` (embeds a taskspecs `TaskSpec`) |
| task.progress | `schemas/task_progress.v1.json` | `TaskProgress` |
| task.report | `schemas/task_report.v1.json` | `TaskReportMessage` (embeds a taskspecs `TaskReport`) |
| task.cancel | `schemas/task_cancel.v1.json` | `TaskCancel` |
| ping / pong | `schemas/ping.v1.json` / `pong.v1.json` | `Ping` / `Pong` |

Every frame carries `schema_version: 1`. Envelopes are forward-compatible:
unknown top-level fields are preserved (in `model.extra`) and re-emitted.

### Encode / decode

```python
from stapel_runner_protocol import Hello, encode, decode

frame = encode(Hello(project_id="brave-falcon-1042", runner_version="0.1.0",
                     capabilities=["agent-sdk", "subprocess"]))
msg = decode(frame, validate=True)   # dispatches on `type`, validates the schema
```

### Idempotency and resume

Progress is idempotent by `(task_id, seq)`; hub→runner commands are buffered and
replayed. The state machine is transport-agnostic and synchronous:

```python
from stapel_runner_protocol import ConnectionState, TaskCancel

hub, runner = ConnectionState("hub"), ConnectionState("runner")
c1 = hub.emit(TaskCancel(task_id="T-1", reason="a"))   # seq assigned = 1
c2 = hub.emit(TaskCancel(task_id="T-1", reason="b"))   # seq = 2
runner.receive(c1)                                     # runner got 1, then dropped

resume = runner.resume_map()          # {"T-1": 1}  -> goes in hello.resume
replay = hub.replay_for(resume)       # {"T-1": [c2]}  -> hub re-sends the tail
```

A runner may safely re-send progress from its last checkpoint (a git commit)
after a reconnect — the hub drops the duplicate seqs.

## Harness adapters

```python
adapter.open_session(role_spec) -> Session
Session.turn(prompt)            -> TurnResult   # {text, usage}
adapter.oneshot(role_spec, prompt) -> TurnResult
Session.close() / adapter.close()
```

`TurnResult.usage` is **always** the strict five-component
`stapel_taskspecs.UsageSplit` and is validated on construction — a protocol
condition, not a convenience (without the `thinking` column, reasoning-class
economics are understated, studio-design 7.16).

```python
from stapel_runner_protocol import RoleSpec, SubprocessAdapter

role = RoleSpec.from_invocation(assign.invocation, role="coder")
adapter = SubprocessAdapter(command=["my-harness", "--json"])
result = adapter.oneshot(role, "implement the task")
result.text, result.usage.total_tokens
```

Reference adapters:

- **`AgentSdkAdapter`** — a persistent claude-agent-sdk session per task
  (append-only, cache_read-friendly — the coder's slice configuration). The SDK
  is an optional extra; inject a `client_factory` to test or to wire a custom
  client.
- **`SubprocessAdapter`** — a JSONL stream to a child process
  (`{"type":"turn"}` in, `{"type":"result","text","usage"}` out). Inject `spawn`
  to test against a fake child.

## Out of scope (moat)

Anti-cheat rules, permission policies, concrete system prompts, and routing
config are **not** here and never will be. Roles, progress kinds, capabilities
and statuses are open strings, not closed enums (a closed enum would leak
private routing policy into an OSS schema). This library carries the *shape* and
the *sequencing discipline*, nothing of the pipeline's brains.

## License

MIT.
