from mcp.clients.cms import cms_client  # noqa: F401 (kept for test patch target)
from mcp.tool_registry import PAGINATION_PROPERTIES, tool

from mcp.cms.helpers import CmsToolModule

_path_for = "/category/{}/".format


class CmsCategoriesTools(CmsToolModule):
    @tool(
        name="list_editorial_categories",
        description=(
            "List all CMS categories with pagination. Returns every category including unpublished ones. "
            "NOTE: if the user only needs published categories, prefer the CDS fetch_published_categories tool. "
            "Use this when the user needs drafts, unpublished categories, or management operations. "
            "Returns results directly — no confirmation step needed."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                **PAGINATION_PROPERTIES,
            },
        },
    )
    def list_editorial_categories(self, credentials: dict, args: dict):
        return self.list_resource(credentials, args, path="/category/")

    @tool(
        name="get_editorial_category",
        description=(
            "Retrieve a single CMS category by ID. Returns full details including unpublished fields. "
            "NOTE: if the user only needs basic published data, prefer the CDS fetch_published_category tool. "
            "Always ask the user for the category ID before calling if not already provided. "
            "Returns results directly — no confirmation step needed."
        ),
        inputSchema={
            "type": "object",
            "required": ["id"],
            "properties": {"id": {"type": "integer", "description": "Category ID"}},
        },
    )
    def get_editorial_category(self, credentials: dict, args: dict):
        return self.get_resource(credentials, args, path_for=_path_for)

    @tool(
        name="create_category",
        description=(
            "Create a new category in the CMS. "
            "BEFORE calling: confirm all details with the user — at minimum name and english_name. "
            "Workflow: dry_run=true (default) shows a full preview of what will be created — no changes made. "
            "Once the user confirms the preview, call again with dry_run=false to create. "
            "Immutable after creation: english_name, slug, parent_category, content_type."
        ),
        inputSchema={
            "type": "object",
            "required": ["name", "english_name"],
            "properties": {
                "name":                 {"type": "string", "minLength": 1,  "description": "Category name"},
                "english_name":         {"type": "string", "minLength": 1,  "description": "English name — used for permalink generation. Immutable after creation."},
                "slug":                 {"type": "string",  "description": "Custom slug (auto-generated from english_name if omitted). Immutable after creation."},
                "meta_title":           {"type": "string",  "description": "SEO title"},
                "h1_tag":               {"type": "string",  "description": "H1 heading tag"},
                "meta_description":     {"type": "string",  "description": "SEO description"},
                "parent_category":      {"type": "integer", "description": "Parent category ID. Immutable after creation."},
                "priority":             {"type": "integer", "description": "Priority level (1–1000)"},
                "content":              {"type": "string",  "description": "Category description (HTML)"},
                "category_brand_color": {"type": "string",  "description": "Brand color in hex (e.g. #EF4444)"},
                "content_type":         {"type": "string",  "description": "Content type filter e.g. Article, Web Story. Immutable after creation."},
                "dry_run":              {"type": "boolean", "description": "true = preview only, no changes (default); false = create for real"},
            },
        },
    )
    def create_category(self, credentials: dict, args: dict):
        return self.create_resource(credentials, args, resource="Category", path="/category/")

    @tool(
        name="update_category",
        description=(
            "Update an existing category. "
            "BEFORE calling: confirm the category ID and all fields to change with the user. "
            "Workflow: dry_run=true (default) fetches current state and shows a field-by-field diff — no changes made. "
            "Show the diff to the user. Once they confirm, call again with dry_run=false to apply. "
            "Immutable fields that cannot be changed: english_name, slug, content_type."
        ),
        inputSchema={
            "type": "object",
            "required": ["id"],
            "properties": {
                "id":                   {"type": "integer", "description": "Category ID"},
                "name":                 {"type": "string",  "description": "New category name"},
                "meta_title":           {"type": "string",  "description": "New SEO title"},
                "meta_description":     {"type": "string",  "description": "New SEO description"},
                "content":              {"type": "string",  "description": "New category description (HTML)"},
                "category_brand_color": {"type": "string",  "description": "New brand color (hex)"},
                "priority":             {"type": "integer", "description": "New priority level"},
                "dry_run":              {"type": "boolean", "description": "true = show diff only, no changes (default); false = apply update"},
            },
        },
    )
    def update_category(self, credentials: dict, args: dict):
        return self.update_resource(credentials, args, resource="Category", path_for=_path_for)

    @tool(
        name="delete_category",
        description=(
            "Permanently delete a category. This action CANNOT be undone. "
            "Posts assigned to this category will lose their category assignment. "
            "BEFORE calling: confirm the category ID with the user. "
            "Workflow: dry_run=true (default) fetches and shows the full category details — no deletion. "
            "Show the preview to the user. Once they explicitly confirm deletion, call again with dry_run=false AND confirm_delete=true."
        ),
        inputSchema={
            "type": "object",
            "required": ["id"],
            "properties": {
                "id":             {"type": "integer", "description": "Category ID"},
                "dry_run":        {"type": "boolean", "description": "true = preview only (default); false = delete (also requires confirm_delete=true)"},
                "confirm_delete": {"type": "boolean", "description": "Must be explicitly set to true — together with dry_run=false — to execute the deletion"},
            },
        },
    )
    def delete_category(self, credentials: dict, args: dict):
        return self.delete_resource(
            credentials, args, resource="Category", path_for=_path_for,
            warning="Posts assigned to this category will lose their category assignment.",
        )


cms_categories_tools = CmsCategoriesTools()
SCHEMAS, HANDLERS = cms_categories_tools.build()
