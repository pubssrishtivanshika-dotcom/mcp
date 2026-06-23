"""CMS tool package — aggregates schemas and dispatches tool calls by name."""
import logging

from mcp.tool_dispatch import run_tool_dispatch

from mcp.cms.categories import HANDLERS as _CAT_H
from mcp.cms.categories import SCHEMAS as _CAT_S
from mcp.cms.custom_components import HANDLERS as _CC_H
from mcp.cms.custom_components import SCHEMAS as _CC_S
from mcp.cms.custom_content_types import HANDLERS as _CCT_H
from mcp.cms.custom_content_types import SCHEMAS as _CCT_S
from mcp.cms.live_blog import HANDLERS as _LB_H
from mcp.cms.live_blog import SCHEMAS as _LB_S
from mcp.cms.media import HANDLERS as _MEDIA_H
from mcp.cms.media import SCHEMAS as _MEDIA_S
from mcp.cms.newsletter import HANDLERS as _NEWS_H
from mcp.cms.newsletter import SCHEMAS as _NEWS_S
from mcp.cms.posts import HANDLERS as _POSTS_H
from mcp.cms.posts import SCHEMAS as _POSTS_S
from mcp.cms.reader import HANDLERS as _READER_H
from mcp.cms.reader import SCHEMAS as _READER_S
from mcp.cms.tags import HANDLERS as _TAGS_H
from mcp.cms.tags import SCHEMAS as _TAGS_S
from mcp.cms.validators import HANDLERS as _VAL_H
from mcp.cms.validators import SCHEMAS as _VAL_S

logger = logging.getLogger(__name__)

# Intentionally-excluded CMS endpoints (no tool by design — do not re-scaffold):
#   submit_form — removed: required a browser reCAPTCHA token, unusable in MCP context.

CMS_TOOLS: list[dict] = (
    _CAT_S + _TAGS_S + _POSTS_S + _LB_S
    + _CC_S + _CCT_S + _VAL_S + _MEDIA_S
    + _NEWS_S + _READER_S
)

_HANDLER_REGISTRY: dict = {
    **_CAT_H, **_TAGS_H, **_POSTS_H, **_LB_H,
    **_CC_H,  **_CCT_H,  **_VAL_H,   **_MEDIA_H,
    **_NEWS_H, **_READER_H,
}

# Public set used by the dispatcher to route tool calls without brittle prefix checks.
CMS_TOOL_NAMES: frozenset = frozenset(_HANDLER_REGISTRY.keys())

def _on_error(exc, name):
    """CMS error policy: re-raise (no auth-specific fallback)."""
    raise


def dispatch_cms_tool(credentials: dict, name: str, args: dict):
    """Resolve name → handler and execute; centralises error handling."""
    return run_tool_dispatch(
        credentials, name, args,
        handlers=_HANDLER_REGISTRY,
        logger=logger,
        log_label="dispatch_cms_tool",
        unknown_message="Unknown CMS tool: {name}",
        on_error=_on_error,
    )
