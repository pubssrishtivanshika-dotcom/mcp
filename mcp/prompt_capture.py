"""Prompt side-channel handling for tool calls.

Clients may smuggle the user/LLM prompt text into a tool call via the
``_prompt`` / ``prompt`` argument keys. Those are observability hints, not real
tool inputs, so they must be stripped before the arguments reach the handler
(otherwise schema validation would reject the unexpected keys).
"""
from __future__ import annotations

# Argument keys clients use to pass prompt context; stripped before dispatch.
_PROMPT_ARG_KEYS = ("_prompt", "prompt")


def strip_prompt_from_args(params: dict) -> dict:
    """Return ``params['arguments']`` with the prompt side-channel keys removed.

    The returned dict is a shallow copy, so the caller is free to mutate it and
    the original ``params`` is left untouched.
    """
    args = dict((params or {}).get("arguments") or {})
    for key in _PROMPT_ARG_KEYS:
        args.pop(key, None)
    return args
