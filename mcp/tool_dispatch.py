"""Shared scaffolding for the CDS and CMS tool dispatchers."""


def run_tool_dispatch(credentials, name, args, *, handlers, logger, log_label, unknown_message, on_error):
    """Run a tool dispatch, returning the handler's result or an error payload."""
    args = args or {}
    
    try:
        handler = handlers.get(name)
        if handler is None:
            logger.warning("%s: unknown tool=%s", log_label, name)
            return unknown_message

        return handler(credentials, args)

    except Exception as exc:
        return on_error(exc, name)
