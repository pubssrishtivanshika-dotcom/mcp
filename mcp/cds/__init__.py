"""CDS tool package — aggregates schemas and dispatches tool calls by name."""
import logging

from mcp.clients.shared import REAUTH_HINT
from mcp.tool_dispatch import run_tool_dispatch

from mcp.cds.authors import HANDLERS as _AUTHORS_HANDLERS
from mcp.cds.authors import SCHEMAS as _AUTHORS_SCHEMAS
from mcp.cds.categories import HANDLERS as _CATEGORIES_HANDLERS
from mcp.cds.categories import SCHEMAS as _CATEGORIES_SCHEMAS
from mcp.cds.content import HANDLERS as _CONTENT_HANDLERS
from mcp.cds.content import SCHEMAS as _CONTENT_SCHEMAS
from mcp.cds.posts import HANDLERS as _POSTS_HANDLERS
from mcp.cds.posts import SCHEMAS as _POSTS_SCHEMAS
from mcp.cds.publisher import HANDLERS as _PUBLISHER_HANDLERS
from mcp.cds.publisher import SCHEMAS as _PUBLISHER_SCHEMAS
from mcp.cds.sitemaps import HANDLERS as _SITEMAPS_HANDLERS
from mcp.cds.sitemaps import SCHEMAS as _SITEMAPS_SCHEMAS
from mcp.cds.static_files import HANDLERS as _STATIC_HANDLERS
from mcp.cds.static_files import SCHEMAS as _STATIC_SCHEMAS
from mcp.cds.tags import HANDLERS as _TAGS_HANDLERS
from mcp.cds.tags import SCHEMAS as _TAGS_SCHEMAS

logger = logging.getLogger(__name__)

TOOLS: list[dict] = (
    _POSTS_SCHEMAS
    + _CATEGORIES_SCHEMAS
    + _TAGS_SCHEMAS
    + _AUTHORS_SCHEMAS
    + _PUBLISHER_SCHEMAS
    + _CONTENT_SCHEMAS
    + _SITEMAPS_SCHEMAS
    + _STATIC_SCHEMAS
)

_HANDLER_REGISTRY: dict = {
    **_POSTS_HANDLERS,
    **_CATEGORIES_HANDLERS,
    **_TAGS_HANDLERS,
    **_AUTHORS_HANDLERS,
    **_PUBLISHER_HANDLERS,
    **_CONTENT_HANDLERS,
    **_SITEMAPS_HANDLERS,
    **_STATIC_HANDLERS,
}

def _on_error(exc, name):
    """CDS error policy: surface an upstream 401 as a re-auth prompt, else re-raise."""
    http_status = getattr(getattr(exc, "response", None), "status_code", None)
    if http_status == 401:
        logger.warning("dispatch_cds_tool: CDS rejected credentials (HTTP 401): tool=%s", name)
        return {
            "error": "auth_expired",
            "message": f"Your CDS credentials were rejected (HTTP 401). {REAUTH_HINT}",
        }
    logger.error("dispatch_cds_tool error: tool=%s error=%s", name, exc, exc_info=True)
    raise


def dispatch_cds_tool(credentials: dict, name: str, args: dict):
    """Resolve name → handler and execute; centralises error handling."""
    return run_tool_dispatch(
        credentials, name, args,
        handlers=_HANDLER_REGISTRY,
        logger=logger,
        log_label="dispatch_cds_tool",
        unknown_message="Unknown tool: {name}",
        on_error=_on_error,
    )
