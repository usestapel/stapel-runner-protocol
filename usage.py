"""Usage accounting helpers.

Every turn a harness reports is accounted for with the strict five-component
:class:`stapel_taskspecs.UsageSplit` (``cache_read`` / ``cache_write`` /
``fresh_input`` / ``output`` / ``thinking``). This module maps the common
provider-native usage shapes onto that split; it is the only place a provider's
field names appear.

The split is a protocol condition, not a convenience: without a dedicated
``thinking`` column the economics of reasoning-class models are understated
(studio-design 7.16). Adapters build every ``TurnResult.usage`` through here.
"""

from __future__ import annotations

from typing import Any

from stapel_taskspecs import UsageSplit


def _get(usage: Any, key: str, default: int = 0) -> int:
    if isinstance(usage, dict):
        value = usage.get(key, default)
    else:
        value = getattr(usage, key, default)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def usage_from_anthropic(usage: Any, *, thinking: int = 0) -> UsageSplit:
    """Map an Anthropic-shaped usage object onto a :class:`UsageSplit`.

    Accepts either a dict or an object with attributes. The Anthropic Messages
    API reports ``cache_read_input_tokens`` / ``cache_creation_input_tokens`` /
    ``input_tokens`` / ``output_tokens`` and folds reasoning tokens into
    ``output_tokens``; pass ``thinking`` explicitly when the harness reports a
    separate reasoning-token count (common keys are also checked as a fallback).
    The returned split is validated (five non-negative components).
    """
    if thinking:
        thinking_tokens = int(thinking)
    else:
        thinking_tokens = _get(usage, "thinking_tokens", 0) or _get(usage, "reasoning_tokens", 0)
    return UsageSplit(
        cache_read=_get(usage, "cache_read_input_tokens"),
        cache_write=_get(usage, "cache_creation_input_tokens"),
        fresh_input=_get(usage, "input_tokens"),
        output=_get(usage, "output_tokens"),
        thinking=thinking_tokens,
    ).validate()


def usage_from_mapping(data: Any) -> UsageSplit:
    """Build a :class:`UsageSplit` from a plain five-component mapping.

    Missing components default to zero; the result is validated. Use this for
    subprocess/JSONL harnesses that already emit the canonical split.
    """
    return UsageSplit.from_dict(dict(data or {})).validate()
