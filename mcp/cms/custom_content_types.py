from mcp.clients.cms import cms_client  # noqa: F401 (kept for test patch target)
from mcp.tool_registry import PAGINATION_PROPERTIES, tool

from mcp.cms.helpers import CmsToolModule

_BASE = "/entities/content-type/"
_path_for = (_BASE + "{}/").format


class CustomContentTypesTools(CmsToolModule):
    @tool(
        name="list_content_type_schemas",
        description=(
            "List all custom content type schemas defined for this publisher. "
            "Returns results directly — no confirmation step needed."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                **PAGINATION_PROPERTIES,
            },
        },
    )
    def list_content_type_schemas(self, credentials: dict, args: dict):
        return self.list_resource(credentials, args, path=_BASE)

    @tool(
        name="get_content_type_schema",
        description=(
            "Retrieve a single custom content type schema by ID. "
            "Returns results directly — no confirmation step needed."
        ),
        inputSchema={
            "type": "object",
            "required": ["id"],
            "properties": {"id": {"type": "string", "minLength": 1, "description": "Custom content type schema ID (MongoDB ObjectID)"}},
        },
    )
    def get_content_type_schema(self, credentials: dict, args: dict):
        return self.get_resource(credentials, args, path_for=_path_for)

    @tool(
        name="create_content_type_schema",
        description=(
            "Create a new custom content type schema. "
            "Immutable after creation: api_slug, api_collections_slug. "
            "Workflow: dry_run=true (default) shows a preview — no changes made. "
            "Once confirmed, call again with dry_run=false."
        ),
        inputSchema={
            "type": "object",
            "required": ["name", "api_slug", "api_collections_slug"],
            "properties": {
                "name":                   {"type": "string", "minLength": 1,  "description": "Display name (e.g. 'Movies')"},
                "type":                   {"type": "string",  "description": "Schema type: Collection (default)"},
                "api_slug":               {"type": "string", "minLength": 1,  "description": "Singular API slug. Immutable after creation."},
                "api_collections_slug":   {"type": "string", "minLength": 1,  "description": "Plural API slug. Immutable after creation."},
                "response_type":          {"type": "string",  "description": "Response format — json (default)"},
                "field_types":            {"type": "array",   "description": "Array of field definitions. Each item: {name (string, required), type (string, required — short_text|long_text|integer|decimal|boolean|email|url|phone_number|json|media|embed|component|dynamic_zone|dynamic_list), meta_data (object), validations (object — required/group_editable), group_id (string)}"},
                "groups":                 {"type": "array",   "description": "Field group definitions"},
                "components":             {"type": "array",   "description": "Associated custom component schema IDs"},
                "settings":               {"type": "object",  "description": "Type-level settings"},
                "global_system_default":  {"type": "boolean", "description": "Mark as system-level default type (default: false)"},
                "dry_run":                {"type": "boolean", "description": "true = preview only, no changes (default); false = create for real"},
            },
        },
    )
    def create_content_type_schema(self, credentials: dict, args: dict):
        return self.create_resource(credentials, args, resource="Custom Content Type", path=_BASE)

    @tool(
        name="update_content_type_schema",
        description=(
            "Update an existing custom content type schema. "
            "Immutable fields: api_slug, api_collections_slug. "
            "Workflow: dry_run=true (default) shows a diff — no changes made."
        ),
        inputSchema={
            "type": "object",
            "required": ["id"],
            "properties": {
                "id":          {"type": "string", "minLength": 1,  "description": "Custom content type schema ID (MongoDB ObjectID)"},
                "name":        {"type": "string",  "description": "New display name"},
                "field_types": {"type": "array",   "description": "Replacement field definitions"},
                "groups":      {"type": "array",   "description": "Updated field group definitions"},
                "components":  {"type": "array",   "description": "Updated associated component schema IDs"},
                "settings":    {"type": "object",  "description": "Updated type-level settings"},
                "dry_run":     {"type": "boolean", "description": "true = show diff only, no changes (default); false = apply update"},
            },
        },
    )
    def update_content_type_schema(self, credentials: dict, args: dict):
        return self.update_resource(credentials, args, resource="Custom Content Type", path_for=_path_for)

    @tool(
        name="delete_content_type_schema",
        description=(
            "Permanently delete a custom content type schema. This action CANNOT be undone. "
            "All content entries based on this schema will lose their schema reference. "
            "Workflow: dry_run=true (default) shows the full schema — no deletion. "
            "Once confirmed, call again with dry_run=false AND confirm_delete=true."
        ),
        inputSchema={
            "type": "object",
            "required": ["id"],
            "properties": {
                "id":             {"type": "string", "minLength": 1,  "description": "Custom content type schema ID (MongoDB ObjectID)"},
                "dry_run":        {"type": "boolean", "description": "true = preview only (default); false = delete"},
                "confirm_delete": {"type": "boolean", "description": "Must be explicitly set to true — together with dry_run=false"},
            },
        },
    )
    def delete_content_type_schema(self, credentials: dict, args: dict):
        return self.delete_resource(
            credentials, args, resource="Custom Content Type", path_for=_path_for,
            warning="All content entries based on this schema will lose their schema reference.",
        )


custom_content_types_tools = CustomContentTypesTools()
SCHEMAS, HANDLERS = custom_content_types_tools.build()
