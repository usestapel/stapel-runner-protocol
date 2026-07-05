# Contributing to stapel-runner-protocol

Thanks for helping. This library defines the wire protocol between the Stapel
Studio orchestrator (hub) and the in-container runner, plus the harness-adapter
seam. Changes here ripple to both ends of every task, so the bar is "would both
the hub and the runner agree on this shape?"

## Scope

In scope: the protocol messages and their JSON Schemas, the transport-agnostic
encode/decode core, the sequencing/resume state machine, the harness-adapter ABC,
and the reference adapters (subprocess JSONL, agent-sdk). Task/report *schemas*
are imported from `stapel-taskspecs` — do not re-define them here.

**Out of scope** (this is the OSS/moat boundary, studio-design §6): anti-cheat
rules, permission policies, concrete system prompts, and routing/escalation
config. Keep value sets (roles, progress kinds, capabilities, statuses) **open**
strings, not closed enums — a closed enum would leak private routing policy into
an OSS schema.

## Development

```sh
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
# reference adapters / transport, if you touch them:
pip install -e ".[dev,websockets,agent-sdk]"
ruff check .
python -m pytest tests/
```

Gates (must be green before merge): `ruff check` (E, F, W; E501 ignored),
`pytest` with the packaged suite, and coverage per `codecov.yml` (patch floor
80%, project ratchet).

## Schema / protocol changes

- Additive, optional field → patch release, same `schema_version`, add a
  CHANGELOG entry and a test.
- Breaking change (new required field, removal/rename, tightened constraint,
  or a change to the sequencing/resume semantics) → a new schema major
  (`*.v2.json`, `schema_version: 2`) and a bumped `protocol_version`, keeping the
  v1 files for a deprecation window.

Every behavioural change needs a CHANGELOG entry and a test in the same PR. New
extension points (a new adapter method, a new message field) must be reflected in
`MODULE.md` in the same PR.

## Conduct

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
