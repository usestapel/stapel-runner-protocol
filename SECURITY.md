# Security Policy

## Reporting a vulnerability

Please report security issues privately to security@stapel.dev. Do not open a
public issue for a suspected vulnerability.

Include a description, reproduction steps, and the affected version. We aim to
acknowledge reports within a few business days and will coordinate a fix and
disclosure timeline with you.

## Scope

`stapel-runner-protocol` is a pure-Python protocol library. Its transport-agnostic
core and message models have no network surface of their own; the optional
`websockets` binding and the reference harness adapters (subprocess, agent-sdk)
do talk to the outside world. The most relevant classes of issue are:

- Message schemas that accept clearly malformed frames, or that fail to validate
  an embedded artifact, in a way that could mislead a consuming hub or runner.
- Sequencing/resume logic that could be driven to mis-apply or drop a frame
  (the idempotency and replay invariants are security-relevant: a dropped or
  double-applied command corrupts the orchestrator's view of a task).
- Decode/parse behaviour that could be abused for resource exhaustion.

Trust boundary reminder: **all content originating in a project container is
untrusted** (studio-design S5). This library validates the *shape* of frames;
it does not, and must not, encode the anti-cheat or permission policy that
decides whether an action is *allowed* — that is enforced in the private
orchestrator. Do not rely on this library for authorization.
