import contextlib
import logging

from mcp.clients.cms import cms_client
from mcp.tool_registry import PAGINATION_PROPERTIES, tool

from mcp.cms import helpers
from mcp.cms.helpers import CmsToolModule

logger = logging.getLogger(__name__)

_path_for = "/post/{}/".format


def _coerce_post_int_fields(payload: dict) -> None:
    for field in ("primary_category", "banner_url", "after_para"):
        if field in payload:
            with contextlib.suppress(ValueError, TypeError):
                payload[field] = int(payload[field])


def _strip_list_brackets(payload: dict) -> None:
    for field in ("tags", "categories"):
        if field in payload and isinstance(payload[field], str):
            payload[field] = payload[field].strip("[]")


def _remap_post_type_error(result: dict, post_type: str) -> dict:
    """Translate the CMS's opaque type-validation bad_request into an actionable message.

    The CMS returns 'Invalid value for key : type' when a post type is not enabled
    for the publisher (e.g. CustomPage is a publisher-gated feature). The raw message
    gives no context on which type failed or how to fix it.
    """
    if not (
        isinstance(result, dict)
        and result.get("error_type") == "bad_request"
        and "invalid value" in result.get("message", "").lower()
        and "type" in result.get("message", "").lower()
    ):
        return result
    return {
        "error_type": "bad_request",
        "message": (
            f"Post type '{post_type}' is not enabled for this publisher. "
            "Contact Publive support to have it activated, or use one of the "
            "standard types: Article, Video, Web Story, Gallery, LiveBlog, CustomPage."
        ),
        "retryable": False,
    }


_NO_DATA_TYPE_HINTS = {
    "Web Story": (
        "Web Story posts require valid AMP story slide markup in the 'content' field. "
        "Create the post via the Publive dashboard first, then update other fields via update_post."
    ),
    "Gallery": (
        "Gallery posts require image data in 'content' as a JSON string: "
        "{\"data\": {\"images\": [{\"id\": <media_id>, \"title\": \"...\", \"description\": \"...\"}]}, "
        "\"content_html\": \"<p>...</p>\"} — each id is a numeric media ID from list_media_assets/get_media_asset."
    ),
}


def _no_data_type_hint(result, post_type: str):
    """If the CMS rejected a create with 'No data provided', return type-specific guidance
    (Web Story / Gallery need real content); otherwise None."""
    if not (
        isinstance(result, dict)
        and result.get("error_type") == "bad_request"
        and "no data provided" in result.get("message", "").lower()
    ):
        return None
    hint = _NO_DATA_TYPE_HINTS.get(post_type)
    return {"error_type": "bad_request", "message": hint, "retryable": False} if hint else None


def _find_recent_post_by_english_title(credentials: dict, english_title):
    """Best-effort: find a recently-created post by english_title. Used to dedup a non-Draft
    POST that returned 5xx but had actually committed, before retrying via the two-step flow."""
    if not english_title:
        return None
    listing = cms_client.get(credentials, "/post/", {"limit": 20})
    if not isinstance(listing, dict) or listing.get("error_type"):
        return None
    for item in (listing.get("results") or listing.get("data") or []):
        if isinstance(item, dict) and item.get("english_title") == english_title:
            return item
    return None


def _is_draft_status(status) -> bool:
    """True if a status value represents Draft (case/space tolerant)."""
    return isinstance(status, str) and status.strip().lower() == "draft"


class CmsPostsTools(CmsToolModule):
    @tool(
        name="list_editorial_posts",
        description=(
            "List all CMS posts with pagination. Includes drafts, published, and scheduled posts. "
            "NOTE: if the user only needs published posts, prefer the CDS fetch_published_posts tool. "
            "Returns results directly — no confirmation step needed."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                **PAGINATION_PROPERTIES,
            },
        },
    )
    def list_editorial_posts(self, credentials: dict, args: dict):
        return self.list_resource(credentials, args, path="/post/")

    @tool(
        name="get_editorial_post",
        description=(
            "Retrieve a single CMS post by ID. Returns full details including draft and scheduled content. "
            "NOTE: if the user only needs basic published data, prefer the CDS fetch_published_post tool. "
            "Returns results directly — no confirmation step needed."
        ),
        inputSchema={
            "type": "object",
            "required": ["id"],
            "properties": {"id": {"type": "integer", "description": "Post ID"}},
        },
    )
    def get_editorial_post(self, credentials: dict, args: dict):
        return self.get_resource(credentials, args, path_for=_path_for)

    @tool(
        name="create_post",
        description=(
            "Create a new post in the CMS. "
            "BEFORE calling: you MUST have all six required fields — title, english_title, type, status, "
            "primary_category, AND contributors (at least one author ID). "
            "contributors is REQUIRED by the API — omitting it causes a hard validation failure. "
            "If the user has not provided an author ID, call fetch_authors first to get one, then ask the user to confirm. "
            "english_title must be plain English text matching the title, NOT a pre-slugified string. "
            "TYPE-SPECIFIC REQUIREMENTS — do NOT attempt to create these without the noted fields: "
            "Video: requires meta_video_embed (the raw <iframe> embed HTML, e.g. a YouTube/Vimeo embed); optionally also meta_video_url (the video page URL). Both are merged into meta_data automatically. "
            "Web Story: requires AMP story slide markup in the content field AND meta_landscape_thumbnail (numeric media ID integer from the Publive media library, e.g. 295255 — use the 'id' field from list_media_assets or get_media_asset). "
            "Gallery: the content field must be a JSON STRING carrying the gallery's image data — "
            "shape: {\"data\": {\"images\": [{\"id\": <media_id>, \"title\": \"...\", \"description\": \"...\"}, ...]}, \"content_html\": \"<p>...</p>\"} "
            "where each id is a numeric media ID from list_media_assets/get_media_asset (use the 'id' field). "
            "Also takes after_para (integer, default 0). NOTE: an empty gallery (no images in data) creates fine as a Draft but FAILS to publish "
            "(the CMS returns 'No data provided', or HTTP 500 if content is plain HTML instead of the JSON shape above). "
            "Article, LiveBlog, CustomPage: no extra required fields beyond the six standard ones. "
            "DRAFT posts (status=Draft): created immediately — no preview/confirmation step. "
            "PUBLISHED/SCHEDULED/APPROVAL PENDING posts: dry_run=true (default) returns a preview of exactly "
            "what will be created and requests confirmation — NO post (not even a draft) is written on this call. "
            "Only after the user confirms do you call again with dry_run=false, which creates the post directly "
            "in the requested status in a single step. "
            "Immutable after creation: english_title, type, slug, meta_data, custom_published_at."
        ),
        inputSchema={
            "type": "object",
            "required": ["title", "english_title", "type", "status", "primary_category", "contributors"],
            "properties": {
                "title":               {"type": "string", "minLength": 1,  "description": "Post headline"},
                "english_title":       {"type": "string", "minLength": 1,  "description": "Plain English headline for slug generation. Immutable after creation."},
                "type":                {"type": "string", "minLength": 1,  "description": "Post type: Article, Video, Web Story, Gallery, LiveBlog, CustomPage. Immutable after creation."},
                "status":              {"type": "string", "minLength": 1,  "description": "Draft, Published, Scheduled, or Approval Pending"},
                "primary_category":    {"type": "integer", "description": "Primary category ID"},
                "contributors":        {"type": "string", "minLength": 1,  "description": "REQUIRED — comma-separated author IDs (e.g. '12' or '12,15')."},
                "content":             {"type": "string",  "description": "HTML body content. For Gallery posts this must instead be a JSON string holding the image data: {\"data\": {\"images\": [{\"id\": <media_id>, \"title\": \"...\", \"description\": \"...\"}]}, \"content_html\": \"<p>...</p>\"}."},
                "tags":                {"type": "string",  "description": "Comma-separated tag IDs"},
                "categories":          {"type": "string",  "description": "Comma-separated additional category IDs"},
                "banner_url":          {"type": "integer", "description": "Media ID for the featured image"},
                "banner_description":  {"type": "string",  "description": "Featured image caption"},
                "short_description":   {"type": "string",  "description": "SEO meta description"},
                "summary":             {"type": "string",  "description": "Post summary"},
                "seo_keyphrase":       {"type": "string",  "description": "Focus keyword for SEO"},
                "slug":                {"type": "string",  "description": "Custom URL slug (auto-generated from english_title if omitted). Immutable after creation."},
                "scheduled_at":        {"type": "string",  "description": "Future publish datetime, format 'YYYY-MM-DD HH:MM:SS' (NOT ISO 8601 with T/Z) — status must be Scheduled"},
                "hide_banner_image":   {"type": "boolean", "description": "Hide the featured image on the post"},
                "custom_published_at":      {"type": "string",  "description": "Backdated publish timestamp ISO 8601. Immutable after creation."},
                "meta_video_url":           {"type": "string",  "description": "Video post only — URL of the video page (e.g. YouTube/Vimeo URL). Merged into meta_data. Immutable after creation."},
                "meta_video_embed":         {"type": "string",  "description": "Video post only (REQUIRED for Video) — raw <iframe> embed HTML for the video (e.g. a YouTube/Vimeo embed). Merged into meta_data. Immutable after creation."},
                "meta_landscape_thumbnail": {"type": "integer", "description": "Web Story only — numeric media ID of the landscape thumbnail image (e.g. 295255). Retrieve the ID from get_media_asset or list_media_assets (use the 'id' field, NOT the path). Merged into meta_data. Immutable after creation."},
                "after_para":              {"type": "integer", "description": "Gallery/Article — paragraph position for injecting content. Defaults to 0 automatically for both Gallery and Article posts if not provided (the CMS requires it but has no default of its own)."},
                "meta_data":               {"type": "object",  "description": "Arbitrary key-value metadata (e.g. access_type). Merged with any type-specific meta fields above. Immutable after creation."},
                "dry_run":                 {"type": "boolean", "description": "true = preview only, no changes (default); false = create for real"},
            },
        },
    )
    def create_post(self, credentials: dict, args: dict):
        dry_run = args.get("dry_run", True)
        payload = {k: v for k, v in args.items() if k != "dry_run" and v is not None and v != ""}

        if not payload.get("contributors"):
            return {
                "error_type": "missing_required_field",
                "message": (
                    "contributors is required to create a post. "
                    "Call fetch_authors to find valid author IDs, then include "
                    "contributors as a comma-separated string (e.g. '12' or '12,15')."
                ),
                "retryable": False,
            }

        # Merge type-specific helper fields into meta_data before any validation.
        _META_HELPER_FIELDS = ("meta_video_url", "meta_video_embed", "meta_landscape_thumbnail")
        meta_extras = {f: payload.pop(f) for f in _META_HELPER_FIELDS if f in payload}
        if meta_extras:
            existing_meta = payload.get("meta_data") or {}
            payload["meta_data"] = {**existing_meta, **meta_extras}

        post_type = payload.get("type", "")
        if post_type == "Video" and not (payload.get("meta_data") or {}).get("meta_video_embed"):
            return {
                "error_type": "missing_required_field",
                "message": (
                    "Video posts require meta_video_embed — the raw <iframe> embed HTML for the video "
                    "(e.g. a YouTube/Vimeo embed). Optionally also pass meta_video_url (the video page URL). "
                    "Both are merged into meta_data automatically."
                ),
                "retryable": False,
            }

        if post_type == "Web Story" and not payload.get("content") and not payload.get("custom_entity"):
            return {
                "error_type": "missing_required_field",
                "message": (
                    "Web Story posts require AMP story slide markup in the 'content' field "
                    "and a numeric media ID in 'meta_landscape_thumbnail' "
                    "(e.g. 295255 — use the 'id' field from list_media_assets or get_media_asset, NOT the file path)."
                ),
                "retryable": False,
            }
        if post_type == "Web Story" and not (payload.get("meta_data") or {}).get("meta_landscape_thumbnail"):
            return {
                "error_type": "missing_required_field",
                "message": (
                    "Web Story posts require meta_landscape_thumbnail — the numeric media ID integer "
                    "of the landscape thumbnail image (e.g. 295255). "
                    "Call list_media_assets or get_media_asset to find the 'id' field of an image asset, "
                    "then pass that integer as meta_landscape_thumbnail."
                ),
                "retryable": False,
            }
        if post_type == "Gallery" and not payload.get("content") and not payload.get("custom_entity"):
            return {
                "error_type": "missing_required_field",
                "message": (
                    "Gallery posts require image data in the 'content' field as a JSON string: "
                    "{\"data\": {\"images\": [{\"id\": <media_id>, \"title\": \"...\", \"description\": \"...\"}]}, "
                    "\"content_html\": \"<p>...</p>\"} — each id is a numeric media ID from list_media_assets/get_media_asset. "
                    "An empty gallery creates as a Draft but cannot be published."
                ),
                "retryable": False,
            }

        if post_type in ("Article", "Gallery"):
            payload.setdefault("after_para", 0)

        _coerce_post_int_fields(payload)
        _strip_list_brackets(payload)

        # Draft: create directly and immediately — no preview/confirmation step.
        if payload.get("status") == "Draft":
            return _remap_post_type_error(cms_client.post(credentials, "/post/", payload), post_type)

        # Non-Draft (Published / Scheduled / Approval Pending): never write on the first call.
        # Show a preview of exactly what will be created and request explicit confirmation.
        # No draft is created here — this only renders the preview.
        if dry_run:
            status = payload.get("status")
            confirm_note = (
                f"\n  This will CREATE and immediately set the post LIVE (status '{status}')."
                if status == "Published"
                else f"\n   This will CREATE the post with status '{status}'."
            )
            preview = helpers.preview_create_op("Post", payload) + confirm_note + (
                "\nTo confirm, call create_post again with the same arguments and dry_run=false."
            )
            return {"dry_run": True, "preview": preview, "confirmation_required": True}

        # Preferred path: create directly in the intended (non-Draft) status with a single POST.
        # The backend supports this (a single POST with status=Published publishes e.g. a Video).
        # The two-step "POST as Draft → PATCH status" fallback below is kept only for the case
        # where a direct non-Draft POST is rejected with a 5xx, so no type can regress.
        intended_status = payload["status"]
        result = _remap_post_type_error(cms_client.post(credentials, "/post/", payload), post_type)

        no_data_hint = _no_data_type_hint(result, post_type)
        if no_data_hint is not None:
            return no_data_hint

        if not (isinstance(result, dict) and result.get("error_type") == "upstream_error"):
            return result

        # Direct create 5xx'd — fall back to the two-step flow. First check whether the 5xx
        # actually committed the post (reuse it rather than create a duplicate).
        existing = _find_recent_post_by_english_title(credentials, payload.get("english_title"))
        if existing is not None:
            post_id = existing.get("id")
        else:
            draft_result = _remap_post_type_error(
                cms_client.post(credentials, "/post/", {**payload, "status": "Draft"}), post_type
            )
            draft_hint = _no_data_type_hint(draft_result, post_type)
            if draft_hint is not None:
                return draft_hint
            if isinstance(draft_result, dict) and "error_type" in draft_result:
                return draft_result
            draft_data = draft_result.get("data", draft_result) if isinstance(draft_result, dict) else draft_result
            post_id = draft_data.get("id") if isinstance(draft_data, dict) else None

        if not post_id:
            return result

        patch = {"status": intended_status}
        if intended_status == "Scheduled" and payload.get("scheduled_at"):
            patch["scheduled_at"] = payload["scheduled_at"]

        patch_result = cms_client.patch(credentials, f"/post/{post_id}/", patch)
        if isinstance(patch_result, dict) and "error_type" in patch_result:
            return {
                "error_type": "partial_success",
                "message": (
                    f"Post was created (ID: {post_id}) but setting status to "
                    f"{intended_status} failed: {patch_result.get('message', 'unknown error')}. "
                    "Use update_post to retry the status change."
                ),
                "post_id": post_id,
                "retryable": False,
            }

        return patch_result

    @tool(
        name="update_post",
        description=(
            "Update an existing post. "
            "DRAFT POSTS: if the post is currently a Draft (or you are setting status=Draft), the update applies immediately — no dry_run step. "
            "LIVE POSTS (Published, Scheduled, Approval Pending — including edits to an already-live post): dry_run=true (default) shows a field-by-field diff — no changes made. "
            "PUBLISHING (status=Published): also requires confirm_publish=true together with dry_run=false. "
            "Cannot be changed after creation: english_title, type, slug."
        ),
        inputSchema={
            "type": "object",
            "required": ["id"],
            "properties": {
                "id":                  {"type": "integer", "description": "Post ID"},
                "title":               {"type": "string",  "description": "New post headline"},
                "content":             {"type": "string",  "description": "New HTML body content. For Gallery posts this must be a JSON string holding image data: {\"data\": {\"images\": [{\"id\": <media_id>, \"title\": \"...\", \"description\": \"...\"}]}, \"content_html\": \"<p>...</p>\"} — required (with image entries) to publish a Gallery."},
                "status":              {"type": "string",  "description": "Draft, Published, Scheduled, or Approval Pending"},
                "primary_category":    {"type": "integer", "description": "New primary category ID"},
                "contributors":        {"type": "string",  "description": "Comma-separated author IDs"},
                "tags":                {"type": "string",  "description": "Comma-separated tag IDs"},
                "categories":          {"type": "string",  "description": "Comma-separated category IDs"},
                "banner_url":          {"type": "integer", "description": "New media ID for featured image"},
                "short_description":   {"type": "string",  "description": "New SEO meta description"},
                "hide_banner_image":   {"type": "boolean", "description": "Hide the featured image"},
                "custom_published_at": {"type": "string",  "description": "Backdated publish timestamp ISO 8601"},
                "scheduled_at":        {"type": "string",  "description": "Future publish datetime, format 'YYYY-MM-DD HH:MM:SS' (NOT ISO 8601 with T/Z)"},
                "dry_run":             {"type": "boolean", "description": "true = show diff only, no changes (default); false = apply update"},
                "confirm_publish":     {"type": "boolean", "description": "Must be true when setting status=Published with dry_run=false."},
            },
        },
    )
    def update_post(self, credentials: dict, args: dict):
        dry_run         = args.get("dry_run", True)
        confirm_publish = args.get("confirm_publish", False)
        post_id         = args["id"]
        changes         = {k: v for k, v in args.items() if k not in ("id", "dry_run", "confirm_publish") and v is not None and v != ""}

        _coerce_post_int_fields(changes)
        _strip_list_brackets(changes)

        # Decide on the post's *effective* status: the incoming status if the caller is
        # changing it, otherwise the post's current status (costs one GET). Only "live"
        # statuses (Published/Scheduled/Approval Pending) go through dry_run — a Draft,
        # whether it stays a draft or is being set to one, is written immediately with no
        # preview. Editing an already-live post still previews (effective status is live).
        current = None
        if "status" in changes:
            effective_status = changes["status"]
        else:
            current = cms_client.get(credentials, f"/post/{post_id}/")
            if isinstance(current, dict) and "error_type" in current:
                return current
            effective_status = current.get("status") if isinstance(current, dict) else None

        if _is_draft_status(effective_status):
            return cms_client.patch(credentials, f"/post/{post_id}/", changes)

        if dry_run:
            if current is None:
                current = cms_client.get(credentials, f"/post/{post_id}/")
                if isinstance(current, dict) and "error_type" in current:
                    return current
            return {"dry_run": True, "preview": helpers.preview_update_op("Post", post_id, current, changes)}

        if changes.get("status") == "Published" and not confirm_publish:
            return {
                "error_type": "confirmation_required",
                "message": (
                    "Publishing a post requires confirm_publish=true. "
                    "Call again with dry_run=false AND confirm_publish=true to publish."
                ),
                "retryable": False,
            }
        return cms_client.patch(credentials, f"/post/{post_id}/", changes)

    @tool(
        name="delete_post",
        description=(
            "Permanently delete a post and all its associated data. This action CANNOT be undone. "
            "Workflow: dry_run=true (default) shows full post details — no deletion. "
            "Once confirmed, call again with dry_run=false AND confirm_delete=true."
        ),
        inputSchema={
            "type": "object",
            "required": ["id"],
            "properties": {
                "id":             {"type": "integer", "description": "Post ID"},
                "dry_run":        {"type": "boolean", "description": "true = preview only (default); false = delete (also requires confirm_delete=true)"},
                "confirm_delete": {"type": "boolean", "description": "Must be explicitly set to true — together with dry_run=false — to execute the deletion"},
            },
        },
    )
    def delete_post(self, credentials: dict, args: dict):
        return self.delete_resource(
            credentials, args, resource="Post", path_for=_path_for,
            warning="This post and ALL its associated data will be permanently removed.",
        )


cms_posts_tools = CmsPostsTools()
SCHEMAS, HANDLERS = cms_posts_tools.build()
