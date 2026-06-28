from mcp.clients.cms import cms_client
from mcp.tool_registry import PAGINATION_PROPERTIES, tool

from mcp.cms.helpers import CmsToolModule, preview_create_op, preview_update_op

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
            "Register an EXTERNALLY-hosted media URL into the CMS library. "
            "Important: this does NOT upload a file — it only records an absolute URL that already exists "
            "elsewhere (e.g. S3, Cloudinary, another CDN). "
            "Use this ONLY for assets ALREADY hosted at a stable, permanent URL OUTSIDE Publive. "
            "It will NOT produce a usable img_src/banner_url path for files that need to live on Publive's "
            "own storage: the resolved path stays the external URL's path, not a real Publive storage key "
            "like 'odishatv/media/media_files/...', so using the returned id as a banner_url/gallery img_src "
            "yields a broken image. "
            "This MCP server has NO real file-upload tool — to get a genuine 'odishatv/media/...' storage key, "
            "upload the file through the Publive dashboard's media library, then reference it by its media id "
            "or path. "
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
        # The media-library endpoint rejects application/json — send multipart/form-data.
        dry_run = args.get("dry_run", True)
        payload = {k: v for k, v in args.items() if k != "dry_run"}
        if dry_run:
            return {"dry_run": True, "preview": preview_create_op("Media", payload)}
        return cms_client.post_form(credentials, _BASE, payload)

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
        # The media-library endpoint rejects application/json — send multipart/form-data.
        dry_run = args.get("dry_run", True)
        item_id = args["id"]
        changes = {k: v for k, v in args.items() if k not in ("id", "dry_run")}
        path    = _path_for(item_id)
        if dry_run:
            current = cms_client.get(credentials, path)
            if isinstance(current, dict) and "error_type" in current:
                return current
            current_data = current.get("data", current) if isinstance(current, dict) else current
            return {"dry_run": True, "preview": preview_update_op("Media", item_id, current_data, changes)}
        return cms_client.patch_form(credentials, path, changes)

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
