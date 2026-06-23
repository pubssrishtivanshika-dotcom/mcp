"""CDS read tools for publisher configuration: branding, navigation, and newsletters."""
import logging

from mcp.clients.cds import cds_client
from mcp.tool_registry import ToolModule, tool

logger = logging.getLogger(__name__)


class PublisherTools(ToolModule):
    client = cds_client

    @tool(
        name="fetch_publisher_profile",
        description="Get publisher profile: branding, logo, accent colors, social links, app store URLs, and site metadata. Always call this first for any branding or publisher identity question — it automatically falls back to footer data if the primary endpoint is unavailable.",
        inputSchema={"type": "object", "properties": {}},
    )
    def fetch_publisher_profile(self, credentials: dict, args: dict):
        result = cds_client.get(credentials, "/publisher-data/")
        if isinstance(result, dict) and "error_type" in result:
            if cds_client.is_not_found(result):
                publisher_id = (credentials or {}).get("publisherId", "unknown")
                logger.warning("fetch_publisher_profile: /publisher-data/ unavailable for publisher=%s — falling back to /footer/", publisher_id)
                return cds_client.get(credentials, "/footer/")
            return result  # surface real errors (auth/upstream) rather than masking them
        return result

    @tool(
        name="fetch_site_navigation",
        description="Get the navigation menu configuration including nested menu items and links.",
        inputSchema={"type": "object", "properties": {}},
    )
    def fetch_site_navigation(self, credentials: dict, args: dict):
        return cds_client.get(credentials, "/navbar/")

    @tool(
        name="fetch_site_footer",
        description="Get the footer layout: menus, links, copyright text, app store URLs, social links, and logo. Use this for footer structure and navigation links. For publisher branding questions (logo, colors, identity), prefer fetch_publisher_profile which aggregates from multiple sources.",
        inputSchema={"type": "object", "properties": {}},
    )
    def fetch_site_footer(self, credentials: dict, args: dict):
        return cds_client.get(credentials, "/footer/")

    @tool(
        name="fetch_newsletter_groups",
        description=(
            "Get all configured newsletter groups with their metadata, logos, and descriptions. "
            "NOTE: this only works for publishers that have a newsletter email configured. "
            "If the publisher has no newsletter set up, this tool returns a not_configured error — "
            "do not retry in that case."
        ),
        inputSchema={"type": "object", "properties": {}},
    )
    def fetch_newsletter_groups(self, credentials: dict, args: dict):
        result = cds_client.get(credentials, "/newsletter-groups/")
        if isinstance(result, dict) and "error_type" in result:
            err_str           = str(result.get("message", "")).lower()
            is_not_configured = (
                cds_client.is_not_found(result)
                or "newsletter"     in err_str
                or "email"          in err_str
                or "not configured" in err_str
            )
            if is_not_configured:
                publisher_id = (credentials or {}).get("publisherId", "unknown")
                logger.warning("fetch_newsletter_groups: publisher=%s has no newsletter configured", publisher_id)
                return {"error": "not_configured", "message": "This publisher has no newsletter email configured. Newsletter groups are unavailable."}
            return result  # surface real errors (auth/upstream) rather than masking them
        return result


publisher_tools = PublisherTools()
SCHEMAS, HANDLERS = publisher_tools.build()
