"""Prompt side-channel handling for tools/call arguments."""

# Argument keys that carry the client-side prompt side-channel, not tool inputs.
_PROMPT_KEYS = ("_prompt", "prompt")


def strip_prompt_from_args(params: dict) -> dict:
    """Return the tool ``arguments`` from a tools/call ``params``, minus prompt keys."""
    arguments = (params or {}).get("arguments") or {}
    if not isinstance(arguments, dict):
        return {}
    return {k: v for k, v in arguments.items() if k not in _PROMPT_KEYS}
