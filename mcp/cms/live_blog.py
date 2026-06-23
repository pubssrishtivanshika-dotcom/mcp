from mcp.clients.cms import cms_client
from mcp.tool_registry import ToolModule, tool

from mcp.cms.helpers import (
    DELETION_REQUIRES_CONFIRMATION,
    preview_create_op,
    preview_delete_op,
    preview_update_op,
    validate_live_blog_post_type,
)


class LiveBlogTools(ToolModule):
    client = cms_client

    @tool(
        name="list_editorial_liveblog_updates",
        description=(
            "List all update entries for a LiveBlog post, ordered by creation time descending. "
            "Only applies to posts with type LiveBlog. "
            "Returns results directly — no confirmation step needed."
        ),
        inputSchema={
            "type": "object",
            "required": ["post_id"],
            "properties": {"post_id": {"type": "integer", "description": "The LiveBlog post ID"}},
        },
    )
    def list_editorial_liveblog_updates(self, credentials: dict, args: dict):
        post_id = args["post_id"]
        return cms_client.get(credentials, f"/post/{post_id}/live-blog-update/")

    @tool(
        name="get_liveblog_update",
        description=(
            "Retrieve a single live blog update entry by its ID. Only applies to posts with type LiveBlog. "
            "Returns results directly — no confirmation step needed."
        ),
        inputSchema={
            "type": "object",
            "required": ["post_id", "id"],
            "properties": {
                "post_id": {"type": "integer", "description": "The LiveBlog post ID"},
                "id":      {"type": "integer", "description": "The live blog update entry ID"},
            },
        },
    )
    def get_liveblog_update(self, credentials: dict, args: dict):
        return cms_client.get(credentials, f"/post/{args['post_id']}/live-blog-update/{args['id']}/")

    @tool(
        name="add_liveblog_update",
        description=(
            "Add a new update entry to a LiveBlog post. Only applies to posts with type LiveBlog. "
            "Workflow: dry_run=true (default) shows a preview — no changes made. "
            "Once the user confirms, call again with dry_run=false to add the entry."
        ),
        inputSchema={
            "type": "object",
            "required": ["post_id", "title", "content"],
            "properties": {
                "post_id":    {"type": "integer", "description": "The LiveBlog post ID"},
                "title":      {"type": "string", "minLength": 1,  "description": "Headline for this update entry"},
                "content":    {"type": "string", "minLength": 1,  "description": "HTML body content for this update entry"},
                "is_pinned":  {"type": "boolean", "description": "Pin this entry to the top of the live blog (default: false)"},
                "dry_run":    {"type": "boolean", "description": "true = preview only, no changes (default); false = create for real"},
            },
        },
    )
    def add_liveblog_update(self, credentials: dict, args: dict):
        dry_run = args.get("dry_run", True)
        post_id = args["post_id"]
        payload = {k: v for k, v in args.items() if k not in ("dry_run", "post_id")}
        err = validate_live_blog_post_type(credentials, post_id)
        if err:
            return err
        if dry_run:
            return {"dry_run": True, "preview": preview_create_op("Live Blog Update", {"post_id": post_id, **payload})}
        return cms_client.post(credentials, f"/post/{post_id}/live-blog-update/", payload)

    @tool(
        name="update_liveblog_update",
        description=(
            "Update an existing live blog update entry. Only applies to posts with type LiveBlog. "
            "Workflow: dry_run=true (default) fetches the current entry and shows a diff — no changes made. "
            "Once confirmed, call again with dry_run=false to apply."
        ),
        inputSchema={
            "type": "object",
            "required": ["post_id", "id"],
            "properties": {
                "post_id":   {"type": "integer", "description": "The LiveBlog post ID"},
                "id":        {"type": "integer", "description": "The live blog update entry ID"},
                "title":     {"type": "string",  "description": "New headline for this update entry"},
                "content":   {"type": "string",  "description": "New HTML body content"},
                "is_pinned": {"type": "boolean", "description": "Pin or unpin this entry"},
                "dry_run":   {"type": "boolean", "description": "true = show diff only, no changes (default); false = apply update"},
            },
        },
    )
    def update_liveblog_update(self, credentials: dict, args: dict):
        dry_run   = args.get("dry_run", True)
        post_id   = args["post_id"]
        update_id = args["id"]
        changes   = {k: v for k, v in args.items() if k not in ("post_id", "id", "dry_run")}
        err = validate_live_blog_post_type(credentials, post_id)
        if err:
            return err
        if dry_run:
            raw = cms_client.get(credentials, f"/post/{post_id}/live-blog-update/{update_id}/")
            if "error_type" in raw:
                return raw
            entry = raw.get("data", raw)
            flat_current = (
                {"title": entry["content"].get("title"), "content": entry["content"].get("content")}
                if isinstance(entry.get("content"), dict)
                else entry
            )
            return {"dry_run": True, "preview": preview_update_op("Live Blog Update", update_id, flat_current, changes)}
        return cms_client.patch(credentials, f"/post/{post_id}/live-blog-update/{update_id}/", changes)

    @tool(
        name="delete_liveblog_update",
        description=(
            "Permanently delete a live blog update entry. This action CANNOT be undone. "
            "Workflow: dry_run=true (default) shows the full entry — no deletion. "
            "Once confirmed, call again with dry_run=false AND confirm_delete=true."
        ),
        inputSchema={
            "type": "object",
            "required": ["post_id", "id"],
            "properties": {
                "post_id":        {"type": "integer", "description": "The LiveBlog post ID"},
                "id":             {"type": "integer", "description": "The live blog update entry ID"},
                "dry_run":        {"type": "boolean", "description": "true = preview only (default); false = delete (also requires confirm_delete=true)"},
                "confirm_delete": {"type": "boolean", "description": "Must be explicitly set to true — together with dry_run=false — to execute the deletion"},
            },
        },
    )
    def delete_liveblog_update(self, credentials: dict, args: dict):
        dry_run        = args.get("dry_run", True)
        confirm_delete = args.get("confirm_delete", False)
        post_id        = args["post_id"]
        update_id      = args["id"]
        err = validate_live_blog_post_type(credentials, post_id)
        if err:
            return err
        if dry_run:
            raw = cms_client.get(credentials, f"/post/{post_id}/live-blog-update/{update_id}/")
            if "error_type" in raw:
                return raw
            entry = raw.get("data", raw)
            return {"dry_run": True, "preview": preview_delete_op("Live Blog Update", update_id, entry)}
        if not confirm_delete:
            return DELETION_REQUIRES_CONFIRMATION
        return cms_client.delete(credentials, f"/post/{post_id}/live-blog-update/{update_id}/")


live_blog_tools = LiveBlogTools()
SCHEMAS, HANDLERS = live_blog_tools.build()
