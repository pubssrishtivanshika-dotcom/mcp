from mcp.clients.cds import cds_client
from mcp.tool_registry import ToolModule, tool

_path_for = "/category/{}/".format


class CdsCategoriesTools(ToolModule):
    client = cds_client

    @tool(
        name="fetch_published_categories",
        description=(
            "List all published categories with hierarchical structure. "
            "If the user only needs a quick count or names, return a summary and offer more details. "
            "If the user needs unpublished categories or management operations, suggest list_editorial_categories instead."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "page":  {"type": "integer"},
                "limit": {"type": "integer"},
            },
        },
    )
    def fetch_published_categories(self, credentials: dict, args: dict):
        return self.list_resource(credentials, args, path="/categories/")

    @tool(
        name="fetch_published_category",
        description=(
            "Get a single published category by ID or slug including SEO metadata and child categories. "
            "If the user only needs basic info (name, slug), return that and offer more. "
            "If the user needs management fields or plans to update, suggest get_editorial_category instead."
        ),
        inputSchema={
            "type": "object",
            "required": ["identifier"],
            "properties": {
                "identifier": {"type": "string", "minLength": 1, "description": "Category ID or slug"},
            },
        },
    )
    def fetch_published_category(self, credentials: dict, args: dict):
        return self.get_resource(credentials, args, path_for=_path_for, id_key="identifier")


cds_categories_tools = CdsCategoriesTools()
SCHEMAS, HANDLERS = cds_categories_tools.build()
