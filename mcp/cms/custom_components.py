import logging

from mcp.clients.cms import cms_client
from mcp.tool_registry import PAGINATION_PROPERTIES, tool

from mcp.cms import helpers
from mcp.cms.helpers import CmsToolModule

logger = logging.getLogger(__name__)

_BASE = "/entities/content-type/custom-component/"
_path_for = (_BASE + "{}/").format


class CustomComponentsTools(CmsToolModule):
    @tool(
        name="list_component_schemas",
        description="List all custom components with pagination. Returns results directly — no confirmation step needed.",
        inputSchema={
            "type": "object",
            "properties": {
                **PAGINATION_PROPERTIES,
            },
        },
    )
    def list_component_schemas(self, credentials: dict, args: dict):
        return self.list_resource(credentials, args, path=_BASE)

    @tool(
        name="get_component_schema",
        description="Retrieve a single custom component by ID. Returns results directly — no confirmation step needed.",
        inputSchema={
            "type": "object",
            "required": ["id"],
            "properties": {"id": {"type": "string", "minLength": 1, "description": "Custom component ID (MongoDB ObjectID, e.g. '6a153d41653f8ae9df571c7e')"}},
        },
    )
    def get_component_schema(self, credentials: dict, args: dict):
        return self.get_resource(credentials, args, path_for=_path_for)

    @tool(
        name="create_component_schema",
        description=(
            "Create a new custom component schema in the CMS. "
            "Custom components are reusable typed-field schemas (like a form builder), NOT HTML templates. "
            "Workflow: dry_run=true (default) shows a preview — no changes made. "
            "Once the user confirms, call again with dry_run=false to create."
        ),
        inputSchema={
            "type": "object",
            "required": ["name"],
            "properties": {
                "name":        {"type": "string", "minLength": 1,  "description": "Display name for the component"},
                "meta_data":   {"type": "object",  "description": "Additional metadata. Supports: {\"description\": \"...\"}"},
                "field_types": {"type": "array",   "description": "Array of field definitions. Each item: {name (string, required), type (string, required — short_text|long_text|integer|decimal|boolean|email|url|phone_number|json|media|embed|component|dynamic_zone), meta_data (object — label/tooltip/type/placeholder/default each as {value:...}), validations (object — required/max_length as {value:...}), group_id (string)}"},
                "settings":    {"type": "object",  "description": "Component-level settings object"},
                "dry_run":     {"type": "boolean", "description": "true = preview only, no changes (default); false = create for real"},
            },
        },
    )
    def create_component_schema(self, credentials: dict, args: dict):
        # Not routed through self.create_resource: this resource needs extra
        # upstream-5xx dedup-retry logic that doesn't fit the generic helper.
        dry_run = args.get("dry_run", True)
        payload = {k: v for k, v in args.items() if k != "dry_run"}
        if dry_run:
            return {"dry_run": True, "preview": helpers.preview_create_op("Custom Component", payload)}
        result = cms_client.post(credentials, _BASE, payload)
        if isinstance(result, dict) and result.get("error_type") == "upstream_error":
            # Check if the server committed before returning 5xx (prevent duplicate)
            listing = cms_client.get(credentials, _BASE, {"limit": 50})
            items   = []
            if isinstance(listing, dict) and not listing.get("error_type"):
                items = listing.get("results") or listing.get("data") or []
            for item in items:
                if isinstance(item, dict) and item.get("name") == payload.get("name"):
                    return item
            result = cms_client.post(credentials, _BASE, payload)
        return result

    @tool(
        name="update_component_schema",
        description=(
            "Update an existing custom component schema. "
            "Workflow: dry_run=true (default) fetches current state and shows a diff — no changes made. "
            "NOTE: sending field_types replaces the entire field definition array."
        ),
        inputSchema={
            "type": "object",
            "required": ["id"],
            "properties": {
                "id":          {"type": "string", "minLength": 1,  "description": "Custom component ID (MongoDB ObjectID)"},
                "name":        {"type": "string",  "description": "New display name for the component"},
                "meta_data":   {"type": "object",  "description": "Updated metadata"},
                "field_types": {"type": "array",   "description": "Replacement field definitions (replaces the whole array). Same schema as create: short_text|long_text|integer|decimal|boolean|email|url|phone_number|json|media|embed|component|dynamic_zone"},
                "settings":    {"type": "object",  "description": "Updated component-level settings"},
                "dry_run":     {"type": "boolean", "description": "true = show diff only, no changes (default); false = apply update"},
            },
        },
    )
    def update_component_schema(self, credentials: dict, args: dict):
        return self.update_resource(credentials, args, resource="Custom Component", path_for=_path_for)

    @tool(
        name="delete_component_schema",
        description=(
            "Permanently delete a custom component. This action CANNOT be undone. "
            "Workflow: dry_run=true (default) shows the full component — no deletion. "
            "Once confirmed, call again with dry_run=false AND confirm_delete=true."
        ),
        inputSchema={
            "type": "object",
            "required": ["id"],
            "properties": {
                "id":             {"type": "string", "minLength": 1, "description": "Custom component ID (MongoDB ObjectID)"},
                "dry_run":        {"type": "boolean", "description": "true = preview only (default); false = delete"},
                "confirm_delete": {"type": "boolean", "description": "Must be explicitly set to true — together with dry_run=false"},
            },
        },
    )
    def delete_component_schema(self, credentials: dict, args: dict):
        return self.delete_resource(credentials, args, resource="Custom Component", path_for=_path_for)


custom_components_tools = CustomComponentsTools()
SCHEMAS, HANDLERS = custom_components_tools.build()
