"""Shared helpers for all CMS write tools: preview formatters and the CmsToolModule base.

``CmsToolModule`` extends :class:`mcp.tool_registry.ToolModule` with the Tier-2/Tier-3
write flow (create preview, update diff, delete double-gate) so each resource module's
handlers are one-liners delegating to ``self.create_resource`` / ``update_resource`` /
``delete_resource``. The preview formatters and ``validate_live_blog_post_type`` stay
module-level — ``live_blog.py`` composes them directly for its nested-path handlers.
"""
from mcp.clients.cms import cms_client
from mcp.tool_registry import PAGINATION_PROPERTIES, ToolModule  # noqa: F401 (re-exported)

# Returned by every delete handler when the caller hasn't passed both
# dry_run=false and confirm_delete=true.
DELETION_REQUIRES_CONFIRMATION: dict = {
    "error_type": "confirmation_required",
    "message": (
        "Deletion requires BOTH dry_run=false AND confirm_delete=true. "
        "Call again with both parameters set to confirm you want to permanently delete this resource."
    ),
    "retryable": False,
}


def format_field_value(v) -> str:
    """Truncate long values for human-readable diff output."""
    if v is None:
        return "(empty)"
    s = str(v)
    return s[:120] + "…" if len(s) > 120 else s


def preview_create_op(resource: str, payload: dict) -> str:
    lines = [
        f"📋  DRY RUN — Create {resource}",
        "─" * 52,
        f"Will create a new {resource.lower()} with the following details:",
        "",
    ]
    for k, v in payload.items():
        lines.append(f"  {k:<28} {format_field_value(v)}")
    lines += [
        "",
        "⚡  No changes have been made.",
        "To proceed, call this tool again with dry_run=false.",
    ]
    return "\n".join(lines)


def preview_update_op(resource: str, item_id, current: dict, changes: dict) -> str:
    lines = [
        f"📋  DRY RUN — Update {resource} #{item_id}",
        "─" * 52,
        "The following fields will change:",
        "",
    ]
    has_diff = False
    for field, new_val in changes.items():
        old_val = current.get(field)
        lines.append(f"  {field:<28} {format_field_value(old_val)}  →  {format_field_value(new_val)}")
        has_diff = True
    if not has_diff:
        lines.append("  (no fields provided — nothing will change)")
    lines += ["", "⚡  No changes have been made.", "To apply, call again with dry_run=false."]
    return "\n".join(lines)


def preview_delete_op(resource: str, item_id, item: dict, warning: str = "") -> str:
    lines = [
        f"📋  DRY RUN — Delete {resource} #{item_id}",
        "─" * 52,
        f"⚠️   WARNING: This will PERMANENTLY delete the following {resource.lower()}:",
        "",
    ]
    for k, v in item.items():
        lines.append(f"  {k:<28} {format_field_value(v)}")
    if warning:
        lines += ["", f"⚠️   {warning}"]
    lines += [
        "",
        "⚡  No changes have been made.",
        "To permanently delete, call again with:",
        "  dry_run=false",
        "  confirm_delete=true",
    ]
    return "\n".join(lines)


def validate_live_blog_post_type(credentials: dict, post_id: int):
    """Return an error dict if post_id doesn't exist or isn't a LiveBlog; else None."""
    raw = cms_client.get(credentials, f"/post/{post_id}/")
    if isinstance(raw, dict) and "error_type" in raw:
        if raw.get("error_type") == "not_found":
            return {
                "error_type": "not_found",
                "message": (
                    f"Post {post_id} was not found in the CMS. "
                    "Check that the post ID is correct and that the post exists."
                ),
                "retryable": False,
            }
        return raw
    # The CMS GET wraps the post under a "data" key — unwrap before reading "type".
    post = raw.get("data", raw) if isinstance(raw, dict) else raw
    if not isinstance(post, dict) or post.get("type") != "LiveBlog":
        return {
            "error_type": "bad_request",
            "message": (
                f"Post {post_id} is a '{post.get('type')}' post, not a LiveBlog. "
                "Live blog updates can only be added to LiveBlog posts."
            ),
            "retryable": False,
        }
    return None


class CmsToolModule(ToolModule):
    """ToolModule for CMS write tools — adds the tiered create/update/delete flow."""

    client = cms_client

    def create_resource(self, credentials: dict, args: dict, *, resource: str, path: str):
        """Tier-2 create: dry_run preview by default, else POST the payload."""
        dry_run = args.get("dry_run", True)
        payload = {k: v for k, v in args.items() if k != "dry_run"}
        if dry_run:
            return {"dry_run": True, "preview": preview_create_op(resource, payload)}
        return self.client.post(credentials, path, payload)

    def update_resource(self, credentials: dict, args: dict, *, resource: str, path_for):
        """Tier-3 update: dry_run diff by default, else PATCH the changes.

        ``path_for`` is a callable mapping the id to its resource path (paths vary,
        e.g. /category/{id}/ vs /entities/content-type/{id}/).
        """
        dry_run = args.get("dry_run", True)
        item_id = args["id"]
        changes = {k: v for k, v in args.items() if k not in ("id", "dry_run")}
        path    = path_for(item_id)
        if dry_run:
            current = self.client.get(credentials, path)
            if "error_type" in current:
                return current
            return {"dry_run": True, "preview": preview_update_op(resource, item_id, current, changes)}
        return self.client.patch(credentials, path, changes)

    def delete_resource(self, credentials: dict, args: dict, *, resource: str, path_for, warning: str = ""):
        """Tier-3 delete: enforces the dry_run + confirm_delete two-gate contract."""
        dry_run        = args.get("dry_run", True)
        confirm_delete = args.get("confirm_delete", False)
        item_id        = args["id"]
        path           = path_for(item_id)
        if dry_run:
            item = self.client.get(credentials, path)
            if "error_type" in item:
                return item
            return {"dry_run": True, "preview": preview_delete_op(resource, item_id, item, warning=warning)}
        if not confirm_delete:
            return DELETION_REQUIRES_CONFIRMATION
        return self.client.delete(credentials, path)
