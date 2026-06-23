from mcp.clients.cms import cms_client  # noqa: F401 (kept for test patch target)
from mcp.tool_registry import PAGINATION_PROPERTIES, tool

from mcp.cms.helpers import CmsToolModule

_path_for = "/tag/{}/".format


class CmsTagsTools(CmsToolModule):
    @tool(
        name="list_editorial_tags",
        description=(
            "List all CMS tags with pagination. Returns all tags including unpublished ones. "
            "NOTE: if the user only needs published tags, prefer the CDS fetch_published_tags tool. "
            "Returns results directly — no confirmation step needed."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                **PAGINATION_PROPERTIES,
            },
        },
    )
    def list_editorial_tags(self, credentials: dict, args: dict):
        return self.list_resource(credentials, args, path="/tag/")

    @tool(
        name="get_editorial_tag",
        description=(
            "Retrieve a single CMS tag by ID. Returns full management details. "
            "NOTE: if the user only needs basic published data, prefer the CDS fetch_published_tag tool. "
            "Returns results directly — no confirmation step needed."
        ),
        inputSchema={
            "type": "object",
            "required": ["id"],
            "properties": {"id": {"type": "integer", "description": "Tag ID"}},
        },
    )
    def get_editorial_tag(self, credentials: dict, args: dict):
        return self.get_resource(credentials, args, path_for=_path_for)

    @tool(
        name="create_tag",
        description=(
            "Create a new tag in the CMS. "
            "BEFORE calling: confirm all details with the user — at minimum name and english_name. "
            "Workflow: dry_run=true (default) shows a full preview — no changes made. "
            "Once the user confirms the preview, call again with dry_run=false to create. "
            "Immutable after creation: english_name, slug."
        ),
        inputSchema={
            "type": "object",
            "required": ["name", "english_name"],
            "properties": {
                "name":             {"type": "string", "minLength": 1, "description": "Tag name"},
                "english_name":     {"type": "string", "minLength": 1, "description": "English name — used for slug generation. Immutable after creation."},
                "slug":             {"type": "string", "description": "Custom slug (auto-generated if omitted). Immutable after creation."},
                "meta_title":       {"type": "string", "description": "SEO title"},
                "meta_description": {"type": "string", "description": "SEO description"},
                "content":          {"type": "string", "description": "Tag description (HTML)"},
                "dry_run":          {"type": "boolean", "description": "true = preview only, no changes (default); false = create for real"},
            },
        },
    )
    def create_tag(self, credentials: dict, args: dict):
        return self.create_resource(credentials, args, resource="Tag", path="/tag/")

    @tool(
        name="update_tag",
        description=(
            "Update an existing tag. "
            "Workflow: dry_run=true (default) fetches current state and shows a diff — no changes made. "
            "Show the diff to the user. Once they confirm, call again with dry_run=false. "
            "Immutable fields: english_name, slug."
        ),
        inputSchema={
            "type": "object",
            "required": ["id"],
            "properties": {
                "id":               {"type": "integer", "description": "Tag ID"},
                "name":             {"type": "string",  "description": "New tag name"},
                "meta_title":       {"type": "string",  "description": "New SEO title"},
                "meta_description": {"type": "string",  "description": "New SEO description"},
                "content":          {"type": "string",  "description": "New tag description (HTML)"},
                "dry_run":          {"type": "boolean", "description": "true = show diff only, no changes (default); false = apply update"},
            },
        },
    )
    def update_tag(self, credentials: dict, args: dict):
        return self.update_resource(credentials, args, resource="Tag", path_for=_path_for)

    @tool(
        name="delete_tag",
        description=(
            "Permanently delete a tag. This action CANNOT be undone. "
            "Workflow: dry_run=true (default) shows full tag details — no deletion. "
            "Once confirmed, call again with dry_run=false AND confirm_delete=true."
        ),
        inputSchema={
            "type": "object",
            "required": ["id"],
            "properties": {
                "id":             {"type": "integer", "description": "Tag ID"},
                "dry_run":        {"type": "boolean", "description": "true = preview only (default); false = delete (also requires confirm_delete=true)"},
                "confirm_delete": {"type": "boolean", "description": "Must be explicitly set to true — together with dry_run=false — to execute the deletion"},
            },
        },
    )
    def delete_tag(self, credentials: dict, args: dict):
        return self.delete_resource(credentials, args, resource="Tag", path_for=_path_for)


cms_tags_tools = CmsTagsTools()
SCHEMAS, HANDLERS = cms_tags_tools.build()
