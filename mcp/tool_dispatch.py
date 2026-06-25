"""Shared scaffolding for the CDS and CMS tool dispatchers.

``dispatch_cds_tool`` and ``dispatch_cms_tool`` were near-identical: both resolve
``name`` → handler, run it, and apply an error-handling policy. The only real
differences are that policy (CDS maps an upstream 401 to an ``auth_expired``
payload; CMS just re-raises) and a couple of labels. Those differences are
injected; everything else lives here once.
"""


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
