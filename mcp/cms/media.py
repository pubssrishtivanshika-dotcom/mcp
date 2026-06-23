from mcp.clients.cms import cms_client  # noqa: F401 (kept for test patch target)
from mcp.tool_registry import PAGINATION_PROPERTIES, tool

from mcp.cms.helpers import CmsToolModule

_BASE = "/media-library/"
_path_for = (_BASE + "{}/").format


class MediaTools(CmsToolModule):
    @tool(
        name="list_media_assets",
        description="List all media assets in the CMS library with pagination. Returns results directly — no confirmation step needed.",
        inputSchema={
            "type": "object",
            "properties": {
                **PAGINATION_PROPERTIES,
            },
        },
    )
    def list_media_assets(self, credentials: dict, args: dict):
        return self.list_resource(credentials, args, path=_BASE)

    @tool(
        name="get_media_asset",
        description="Retrieve a single media asset from the CMS library by ID. Returns results directly — no confirmation step needed.",
        inputSchema={
            "type": "object",
            "required": ["id"],
            "properties": {"id": {"type": "integer", "description": "Media asset ID"}},
        },
    )
    def get_media_asset(self, credentials: dict, args: dict):
        return self.get_resource(credentials, args, path_for=_path_for)

    @tool(
        name="register_media_asset",
        description=(
            "Register an existing media URL into the CMS library. "
            "Important: this does NOT upload files — it registers an external URL (e.g. from S3, Cloudinary). "
            "Immutable after creation: path, type. "
            "Workflow: dry_run=true (default) shows a preview — no changes made. "
            "Once confirmed, call again with dry_run=false."
        ),
        inputSchema={
            "type": "object",
            "required": ["filename", "path"],
            "properties": {
                "filename":  {"type": "string", "minLength": 1,  "description": "Filename (e.g. hero-image.jpg)"},
                "path":      {"type": "string", "minLength": 1,  "description": "Direct external media URL. Immutable after creation."},
                "alt_text":  {"type": "string",  "description": "Alt text for accessibility"},
                "caption":   {"type": "string",  "description": "Caption or description"},
                "source":    {"type": "string",  "description": "Source or credit line (e.g. Reuters, PTI, Staff)"},
                "type":      {"type": "string",  "description": "Image, Video, or File. Immutable after creation."},
                "meta_data": {"type": "object",  "description": "Metadata object e.g. {\"width\": 1200, \"height\": 630}"},
                "dry_run":   {"type": "boolean", "description": "true = preview only, no changes (default); false = register for real"},
            },
        },
    )
    def register_media_asset(self, credentials: dict, args: dict):
        return self.create_resource(credentials, args, resource="Media", path=_BASE)

    @tool(
        name="update_media_asset",
        description=(
            "Update metadata of an existing media asset. "
            "Immutable fields: path, type. "
            "Workflow: dry_run=true (default) shows a diff — no changes made. Once confirmed, call again with dry_run=false."
        ),
        inputSchema={
            "type": "object",
            "required": ["id"],
            "properties": {
                "id":        {"type": "integer", "description": "Media asset ID"},
                "filename":  {"type": "string",  "description": "New filename"},
                "alt_text":  {"type": "string",  "description": "New alt text"},
                "caption":   {"type": "string",  "description": "New caption"},
                "source":    {"type": "string",  "description": "New source or credit line"},
                "meta_data": {"type": "object",  "description": "New metadata object"},
                "dry_run":   {"type": "boolean", "description": "true = show diff only, no changes (default); false = apply update"},
            },
        },
    )
    def update_media_asset(self, credentials: dict, args: dict):
        return self.update_resource(credentials, args, resource="Media", path_for=_path_for)

    @tool(
        name="delete_media_asset",
        description=(
            "Permanently delete a media asset from the library. This action CANNOT be undone. "
            "Posts referencing this media will lose their associated image or file. "
            "Workflow: dry_run=true (default) shows full asset details — no deletion. "
            "Once confirmed, call again with dry_run=false AND confirm_delete=true."
        ),
        inputSchema={
            "type": "object",
            "required": ["id"],
            "properties": {
                "id":             {"type": "integer", "description": "Media asset ID"},
                "dry_run":        {"type": "boolean", "description": "true = preview only (default); false = delete"},
                "confirm_delete": {"type": "boolean", "description": "Must be explicitly set to true — together with dry_run=false"},
            },
        },
    )
    def delete_media_asset(self, credentials: dict, args: dict):
        return self.delete_resource(
            credentials, args, resource="Media", path_for=_path_for,
            warning="Posts referencing this media will lose their associated image or file.",
        )


media_tools = MediaTools()
SCHEMAS, HANDLERS = media_tools.build()
