"""CDS read tools for content metadata: types, ad slots, forms, and URL identification."""
from mcp.clients.cds import cds_client
from mcp.tool_registry import ToolModule, tool


class ContentTools(ToolModule):
    client = cds_client

    @tool(
        name="resolve_url_to_content_type",
        description="Resolve a URL path to its content type: post, category, tag, author, redirect, or not_found.",
        inputSchema={
            "type": "object",
            "required": ["legacy_url"],
            "properties": {
                "legacy_url": {"type": "string", "minLength": 1, "description": "Path to resolve e.g. /guides/getting-started"},
            },
        },
    )
    def resolve_url_to_content_type(self, credentials: dict, args: dict):
        return cds_client.get(credentials, "/identify_url/", {"legacy_url": args["legacy_url"]})

    @tool(
        name="fetch_ad_slots",
        description="Get configured advertisement slots with dimensions, HTML content, and slot type information.",
        inputSchema={"type": "object", "properties": {}},
    )
    def fetch_ad_slots(self, credentials: dict, args: dict):
        return cds_client.get(credentials, "/active-slots/")

    @tool(
        name="fetch_content_type_definitions",
        description="Get all content types configured for this publication (e.g. Article, Video, Web Story) with their API and collection slugs.",
        inputSchema={"type": "object", "properties": {}},
    )
    def fetch_content_type_definitions(self, credentials: dict, args: dict):
        return cds_client.get(credentials, "/content-types/")

    @tool(
        name="fetch_form_schema",
        description="Get a form schema by ID, including field definitions, validation rules, field groups, and captcha configuration.",
        inputSchema={
            "type": "object",
            "required": ["schema_id"],
            "properties": {
                "schema_id":   {"type": "string", "minLength": 1, "description": "24-character hex form schema ID"},
                "page_source": {"type": "string", "description": "Optional context used by the serializer"},
            },
        },
    )
    def fetch_form_schema(self, credentials: dict, args: dict):
        return cds_client.get(credentials, f"/form-schemas/{args['schema_id']}/", {"page_source": args.get("page_source")})


content_tools = ContentTools()
SCHEMAS, HANDLERS = content_tools.build()
