from mcp.clients.cds import cds_client
from mcp.tool_registry import ToolModule, tool

_path_for = "/tag/{}/".format


class CdsTagsTools(ToolModule):
    client = cds_client

    @tool(
        name="fetch_published_tags",
        description=(
            "List all published tags. "
            "If the user only needs a quick count or names, return a summary and offer more. "
            "If the user needs unpublished tags or management operations, suggest list_editorial_tags instead."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "page":  {"type": "integer"},
                "limit": {"type": "integer"},
            },
        },
    )
    def fetch_published_tags(self, credentials: dict, args: dict):
        return self.list_resource(credentials, args, path="/tags/")

    @tool(
        name="fetch_published_tag",
        description=(
            "Get a single published tag by ID or slug. "
            "If the user needs management fields or plans to update, suggest get_editorial_tag instead."
        ),
        inputSchema={
            "type": "object",
            "required": ["identifier"],
            "properties": {
                "identifier": {"type": "string", "minLength": 1, "description": "Tag ID or slug"},
            },
        },
    )
    def fetch_published_tag(self, credentials: dict, args: dict):
        return self.get_resource(credentials, args, path_for=_path_for, id_key="identifier")


cds_tags_tools = CdsTagsTools()
SCHEMAS, HANDLERS = cds_tags_tools.build()
