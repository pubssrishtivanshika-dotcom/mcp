"""Shared scaffolding for the CDS and CMS tool dispatchers.

``dispatch_cds_tool`` and ``dispatch_cms_tool`` were near-identical: both resolve
``name`` → handler, run it, and apply an error-handling policy. The only real
differences are that policy (CDS maps an upstream 401 to an ``auth_expired``
payload; CMS just re-raises) and a couple of labels. Those differences are
injected; everything else lives here once.
"""
from mcp.exceptions import UnknownToolError


def run_tool_dispatch(credentials, name, args, *, handlers,
                      logger, log_label, unknown_message, on_error):
    """Resolve ``name`` → handler and execute it.

    ``on_error(exc, name)`` is called inside the ``except`` block for any failure
    and must either return a fallback value or re-raise (a bare ``raise`` works,
    since the original exception is still active).
    """
    args = args or {}
    try:
        handler = handlers.get(name)
        if handler is None:
            logger.warning("%s: unknown tool=%s", log_label, name)
            raise UnknownToolError(unknown_message.format(name=name))

        return handler(credentials, args)

    except Exception as exc:
        return on_error(exc, name)
