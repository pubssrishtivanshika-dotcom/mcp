"""CDS sitemap tools — return XML wrapped in the standard CDS JSON envelope."""
from mcp.clients.cds import cds_client
from mcp.tool_registry import ToolModule, tool

_SITEMAP_PATHS = {
    "index":       "/sitemap/allcontent-sitemap.xml/",
    "web_index":   "/sitemap/webcontent-sitemap.xml/",
    "web_stories": "/sitemap/webstory-sitemap.xml/",
    "news":        "/sitemap/news-sitemap.xml/",
    "categories":  "/sitemap/category-sitemap.xml/",
}


class SitemapsTools(ToolModule):
    client = cds_client

    @tool(
        name="fetch_sitemap",
        description=(
            "Get a sitemap XML file by type. "
            "Use 'index' for the master sitemapindex linking all content. "
            "Use 'web_index' for the paginated article sitemap index (lists dates for fetch_sitemap_page). "
            "Use 'web_stories' for the web story sitemap index. "
            "Use 'news' for the Google News sitemap. "
            "Use 'categories' for the categories sitemap."
        ),
        inputSchema={
            "type": "object",
            "required": ["type"],
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["index", "web_index", "web_stories", "news", "categories"],
                    "description": "Which sitemap to fetch",
                },
            },
        },
    )
    def fetch_sitemap(self, credentials: dict, args: dict):
        sitemap_type = args["type"]
        path = _SITEMAP_PATHS[sitemap_type]
        return cds_client.get(credentials, path)

    @tool(
        name="fetch_sitemap_page",
        description=(
            "Get a paginated date-stamped sitemap — either an article sitemap (sitemap_{date}.xml) "
            "or a web story sitemap (webstory_sitemap_{date}.xml). "
            "Discover valid date values from fetch_sitemap(type='web_index') or fetch_sitemap(type='web_stories') first."
        ),
        inputSchema={
            "type": "object",
            "required": ["date"],
            "properties": {
                "date": {"type": "string", "minLength": 1, "description": "Date partition string (e.g. 2026-05-01) from the web_index or web_stories sitemap"},
                "type": {"type": "string", "description": "Sitemap type: article (default) or webstory"},
            },
        },
    )
    def fetch_sitemap_page(self, credentials: dict, args: dict):
        date         = args["date"]
        sitemap_type = args.get("type", "article")
        if sitemap_type == "webstory":
            path = f"/sitemap/webstory_sitemap_{date}.xml/"
        else:
            path = f"/sitemap/sitemap_{date}.xml/"
        return cds_client.get(credentials, path)


sitemaps_tools = SitemapsTools()
SCHEMAS, HANDLERS = sitemaps_tools.build()
