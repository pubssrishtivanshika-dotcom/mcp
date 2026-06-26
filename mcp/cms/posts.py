import contextlib
import json
import logging
import re

from mcp.clients.cms import cms_client
from mcp.tool_registry import PAGINATION_PROPERTIES, tool

from mcp.cms import helpers
from mcp.cms.helpers import CmsToolModule

logger = logging.getLogger(__name__)

_path_for = "/post/{}/".format


# A Thumbor dimension segment, e.g. '750x500' / '0x500' / '-100x100' (negative = flip).
_THUMBOR_DIM_SEG = re.compile(r"^-?\d+x-?\d+$")


def _normalize_img_src(value):
    """Reduce a media reference to the bare relative storage key the CMS gallery stores
    (e.g. 'odishatv/media/media_files/foo.jpg').

    The dashboard stores img_src as a relative path, NOT a full CDN URL. This accepts
    either form: a relative key is returned unchanged; a full CDN URL is stripped of its
    scheme+host and any leading Thumbor transform prefix.

    Thumbor prefixes stack in a fixed order and any subset may be present, e.g.
        unsafe/fit-in/750x500/filters:quality(80)/filters:format(webp)/odishatv/media/...
    so we strip control segments from the head in a loop until the next segment is the
    real storage key:
      - a leading 'unsafe' segment (case-insensitive),
      - 'fit-in' followed by its dimension argument ('<W>x<H>'),
      - any number of 'filters:...' segments.
    The previous implementation only stripped 'fit-in' when it was the FIRST segment, so a
    real 'unsafe/fit-in/.../...' URL slipped through unstripped and was stored as a broken
    img_src/banner_url.
    """
    if not isinstance(value, str) or not value.strip():
        return value
    v = value.strip()
    if v.startswith(("http://", "https://")):
        rest = v.split("://", 1)[1]
        v = rest.split("/", 1)[1] if "/" in rest else ""
    segs = v.lstrip("/").split("/")
    while segs:
        head = segs[0]
        if head.lower() == "unsafe":
            segs.pop(0)
        elif head.lower() == "fit-in":
            segs.pop(0)                                   # 'fit-in'
            if segs and _THUMBOR_DIM_SEG.match(segs[0]):
                segs.pop(0)                               # dimensions, e.g. '750x500'
        elif head.startswith("filters:"):
            segs.pop(0)
        else:
            break
    return "/".join(segs)


def _resolve_media_url(credentials: dict, media_id):
    """Resolve a CMS media-library id to the storage path the gallery stores
    (e.g. 'odishatv/media/media_files/foo.jpg').

    Returns (path, error); exactly one is non-None:
      - (path, None)  on success,
      - (None, error) on ANY failure, where error is the CMS client's own normalized
        error dict ({error_type, message, retryable}).

    Crucially this no longer collapses every failure to None. A 404 ('not_found') means
    the id genuinely does not exist; a 401/403 ('auth_error'/'bad_request'), timeout, or
    5xx ('upstream_error') is a REAL upstream failure that must NOT be reported to the
    caller as a bad media id. Callers inspect error['error_type'] / error['message'] to
    surface the true cause.
    """
    raw = cms_client.get(credentials, f"/media-library/{media_id}/")
    if isinstance(raw, dict) and raw.get("error_type"):
        return None, raw
    if not isinstance(raw, dict):
        return None, {
            "error_type": "system_error",
            "message": f"Unexpected (non-object) response while resolving media id {media_id}.",
            "retryable": False,
        }
    data = raw.get("data", raw)
    if not isinstance(data, dict):
        data = raw
    # Prefer the relative 'path' (the storage key the writer expects); fall back to
    # absolute_path (a full CDN URL) which callers normalize back down to the relative key.
    path = data.get("path") or data.get("absolute_path")
    if not path:
        return None, {
            "error_type": "bad_request",
            "message": (
                f"Media id {media_id} exists but has no usable 'path'/'absolute_path' field "
                "to use as an image source."
            ),
            "retryable": False,
        }
    return path, None


def _resolve_media_error_message(prefix: str, media_id, error: dict, fallback_hint: str) -> dict:
    """Build a caller-facing error that surfaces the REAL underlying CMS failure
    (e.g. 'auth_error: ...', 'not_found: ...') rather than the old blanket
    'could not resolve media id X'. Preserves the upstream error_type/retryable."""
    error_type = error.get("error_type", "bad_request") if isinstance(error, dict) else "bad_request"
    detail     = error.get("message", "unknown error") if isinstance(error, dict) else "unknown error"
    if error_type == "not_found":
        cause = (
            f"media id {media_id} was not found — the id is wrong. "
            "Verify it via get_media_asset / list_media_assets (use the 'id' field)."
        )
    else:
        cause = (
            f"resolving media id {media_id} failed with a real upstream error "
            f"({error_type}: {detail}) — this is NOT a bad id."
        )
    return {
        "error_type": error_type,
        "message": f"{prefix} {cause} {fallback_hint}",
        "retryable": error.get("retryable", False) if isinstance(error, dict) else False,
    }


def _build_gallery_slide(credentials: dict, slide: dict):
    """Normalize one caller-supplied slide into the CMS image-slide item shape used by
    BOTH Gallery (content.data.gallery[]) and Web Story (content.data.web_story[]) — the
    two share an identical slide structure.

    img_src is the relative media path — a caller may pass it directly (or a full CDN URL,
    normalized), or a numeric media id which is resolved here. Optional text fields
    (title/desc/alt_text/caption_text) are emitted ONLY when non-empty, matching what the
    dashboard actually writes (real slides omit empty keys rather than storing ""/null).
    Returns (item, error); exactly one is non-None.
    """
    img_src = slide.get("img_src")
    if not img_src:
        media_id = slide.get("id", slide.get("media_id"))
        if media_id is not None:
            img_src, err = _resolve_media_url(credentials, media_id)
            if err is not None:
                return None, _resolve_media_error_message(
                    "Slide image could not be set:",
                    media_id,
                    err,
                    "Alternatively pass img_src (the media path) directly.",
                )
    if not img_src:
        return None, {
            "error_type": "bad_request",
            "message": "Each slide requires img_src (the media path) or a numeric media id.",
            "retryable": False,
        }
    item = {
        "type":    slide.get("type", "Image"),
        "img_src": _normalize_img_src(img_src),
    }
    # Only include optional text fields when they actually carry a value — this matches the
    # dashboard-written shape, which omits empty desc/caption_text/title/alt_text entirely.
    for src_key, out_key in (("title", "title"), ("desc", "desc"), ("alt_text", "alt_text"),
                             ("caption_text", "caption_text")):
        value = slide.get(src_key)
        if src_key == "desc" and not value:
            value = slide.get("description")
        if value:
            item[out_key] = value
    return item, None


def _build_slide_content(credentials: dict, slides: list, data_key: str, content_html: str = ""):
    """Serialize image slides into the content JSON STRING the CMS stores under
    content.data.<data_key> — 'gallery' for Gallery posts, 'web_story' for Web Story posts
    (both read by the dashboard editor and the public page). Returns (content_string, error);
    exactly one is non-None.
    """
    items = []
    for slide in slides:
        if not isinstance(slide, dict):
            return None, {
                "error_type": "bad_request",
                "message": f"Each {data_key} slide must be an object with img_src (or a media id) and optional title/desc/alt_text/caption_text.",
                "retryable": False,
            }
        item, err = _build_gallery_slide(credentials, slide)
        if err is not None:
            return None, err
        items.append(item)
    # Match exactly what the dashboard / public page read & write: just {"data": {<key>: [...]}}.
    # No unconditional "web_story": null, no top-level "content_html" unless body HTML was given.
    blob = {"data": {data_key: items}}
    if content_html:
        blob["content_html"] = content_html
    return json.dumps(blob, ensure_ascii=False), None


def _build_gallery_content(credentials: dict, slides: list, content_html: str = ""):
    """Serialize Gallery slides into content.data.gallery (see _build_slide_content)."""
    return _build_slide_content(credentials, slides, "gallery", content_html)


def _build_web_story_content(credentials: dict, slides: list, content_html: str = ""):
    """Serialize Web Story slides into content.data.web_story (see _build_slide_content).

    Real Web Story posts store the SAME image-slide structure as Gallery, keyed 'web_story'
    instead of 'gallery' — NOT hand-written AMP markup."""
    return _build_slide_content(credentials, slides, "web_story", content_html)


def _resolve_banner_url(credentials: dict, value):
    """Resolve a featured-image reference to the relative media path the CMS stores
    (e.g. 'odishatv/media/media_files/foo.jpg') — the form the dashboard's featured-image
    widget reads. Accepts a numeric media id (resolved via the media library), a relative
    path, or a full CDN URL (normalized). Returns (resolved, error); exactly one is non-None.

    A numeric media id that fails to resolve is a hard error: forwarding the bare id to the
    CMS only yields the opaque 'Banner URL must be a valid media object ID' rejection, so we
    surface the REAL cause instead (a wrong id vs. an auth/permission/timeout failure).
    """
    if isinstance(value, int) or (isinstance(value, str) and value.strip().isdigit()):
        path, err = _resolve_media_url(credentials, int(value))
        if err is not None:
            return None, _resolve_media_error_message(
                "Featured image (banner_url) could not be set:",
                value,
                err,
                "Alternatively pass banner_url as the relative media path directly "
                "(e.g. 'odishatv/media/media_files/foo.jpg').",
            )
        return _normalize_img_src(path), None
    if isinstance(value, str):
        return _normalize_img_src(value), None
    return value, None


def _coerce_post_int_fields(payload: dict) -> None:
    # NOTE: banner_url is intentionally NOT coerced here. It is stored as the relative media
    # path the dashboard's featured-image widget reads (resolved upstream by
    # _resolve_banner_url); casting it to int would corrupt that path.
    for field in ("primary_category", "after_para"):
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
        "Web Story posts require slides. Pass web_story_images as an array of "
        "{img_src (media path) OR id (numeric media id), title, desc, alt_text} — the tool serializes "
        "these into content.data.web_story, the image-slide shape the dashboard and public page read "
        "(a real Web Story is image slides, NOT AMP markup). Alternatively pass raw AMP story markup "
        "in the 'content' field."
    ),
    "Gallery": (
        "Gallery posts require slides. Pass gallery_images as an array of "
        "{img_src (media path) OR id (numeric media id), title, desc, alt_text, caption_text} — "
        "the tool serializes these into content.data.gallery, the shape the dashboard 'Gallery Slides' "
        "editor and the public page both read. An empty gallery creates as a Draft but cannot be published."
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
            "Web Story: pass web_story_images — an array of image slides, each {img_src (media path) OR id (numeric media id from "
            "list_media_assets/get_media_asset), title, desc, alt_text}. The tool serializes these into content.data.web_story — the "
            "exact image-slide shape the dashboard AND public page read (a real Web Story is image slides, NOT hand-written AMP markup). "
            "Alternatively, for an AMP-template Web Story, pass raw AMP story slide markup in the content field instead. "
            "meta_landscape_thumbnail (numeric media ID, e.g. 295255 — the 'id' from list_media_assets/get_media_asset) is OPTIONAL. "
            "Gallery: pass gallery_images — an array of slides, each {img_src (media path) OR id (numeric media id from "
            "list_media_assets/get_media_asset), title, desc, alt_text, caption_text}. The tool serializes these into the "
            "content field as content.data.gallery — the exact shape the dashboard 'Gallery Slides' editor AND the public "
            "page both read. (Do NOT hand-build the content string; prefer gallery_images so editor and site stay in sync.) "
            "Also takes after_para (integer, default 0). NOTE: an empty gallery (no slides) creates fine as a Draft but FAILS to publish. "
            "Article, LiveBlog, CustomPage: no extra required fields beyond the six standard ones. "
            "MEDIA SOURCING for banner_url / gallery img_src: pass a relative Publive media path "
            "(e.g. 'odishatv/media/media_files/foo.jpg') or a numeric media id from "
            "list_media_assets/get_media_asset. Use register_media_asset ONLY for assets ALREADY hosted "
            "at a stable, permanent URL OUTSIDE Publive — it merely records that external URL and will NOT "
            "produce a usable img_src/banner_url path for files that need to live on Publive's own storage. "
            "(This MCP server has no file-upload tool; upload via the Publive dashboard to get a real "
            "'odishatv/media/...' storage key.) "
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
                "content":             {"type": "string",  "description": "HTML body content. For Gallery posts prefer gallery_images instead — if you do pass content for a Gallery it must be a JSON string of {\"data\": {\"gallery\": [{\"type\": \"Image\", \"img_src\": \"<media path>\", \"title\": \"...\", \"desc\": \"...\", \"alt_text\": \"...\", \"caption_text\": null}]}} (the exact shape the dashboard writes — NO \"web_story\" key, NO top-level \"content_html\" unless you actually have body HTML)."},
                "gallery_images":      {"type": "array",   "description": "Gallery posts only — slides, serialized into content.data.gallery (the shape the dashboard 'Gallery Slides' editor and the public page both read). Preferred over a raw content string. Each item: img_src (relative media path, or a full CDN URL which is normalized) OR id (numeric media id, resolved to the media path automatically); plus optional title, desc, alt_text, caption_text.",
                                        "items": {"type": "object", "properties": {
                                            "img_src":      {"type": "string",  "description": "Slide image — the relative media path the CMS stores (e.g. 'odishatv/media/media_files/foo.jpg'). A full CDN URL is also accepted and normalized to the path automatically."},
                                            "id":           {"type": "integer", "description": "Numeric media id (alternative to img_src; resolved to the media path automatically)."},
                                            "type":         {"type": "string",  "description": "Slide type — defaults to 'Image'."},
                                            "title":        {"type": "string",  "description": "Slide title."},
                                            "desc":         {"type": "string",  "description": "Slide description text."},
                                            "alt_text":     {"type": "string",  "description": "Image alt text."},
                                            "caption_text": {"type": "string",  "description": "Caption text. Omitted from the stored slide when empty."},
                                        }}},
                "web_story_images":    {"type": "array",   "description": "Web Story posts only — image slides, serialized into content.data.web_story (the image-slide shape the dashboard and public page read; a real Web Story is image slides, NOT AMP markup). Preferred over a raw content string. Each item: img_src (relative media path, or a full CDN URL which is normalized) OR id (numeric media id, resolved to the media path automatically); plus optional title, desc, alt_text.",
                                        "items": {"type": "object", "properties": {
                                            "img_src":      {"type": "string",  "description": "Slide image — the relative media path the CMS stores (e.g. 'odishatv/media/post_attachments/uploadimage/library/16_9/16_9_0/foo.jpg'). A full CDN URL is also accepted and normalized."},
                                            "id":           {"type": "integer", "description": "Numeric media id (alternative to img_src; resolved to the media path automatically)."},
                                            "type":         {"type": "string",  "description": "Slide type — defaults to 'Image'."},
                                            "title":        {"type": "string",  "description": "Slide title."},
                                            "desc":         {"type": "string",  "description": "Slide description text."},
                                            "alt_text":     {"type": "string",  "description": "Image alt text."},
                                        }}},
                "tags":                {"type": "string",  "description": "Comma-separated tag IDs"},
                "categories":          {"type": "string",  "description": "Comma-separated additional category IDs"},
                "banner_url":          {"type": ["integer", "string"], "description": "Featured image. Pass a numeric media id (resolved to its media path automatically), the relative media path (e.g. 'odishatv/media/media_files/foo.jpg'), or a full CDN URL. Stored as the relative path the dashboard's featured-image widget reads."},
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
                "meta_landscape_thumbnail": {"type": "integer", "description": "Web Story only (OPTIONAL) — numeric media ID of the landscape thumbnail image (e.g. 295255). Retrieve the ID from get_media_asset or list_media_assets (use the 'id' field, NOT the path). Merged into meta_data. Immutable after creation."},
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

        # Gallery / Web Story: serialize structured image slides into the content blob the
        # dashboard editor AND public page read (content.data.gallery / content.data.web_story).
        # These helper arrays never go to the API as top-level fields, so pop them regardless
        # of type.
        gallery_images   = payload.pop("gallery_images", None)
        web_story_images = payload.pop("web_story_images", None)
        if post_type == "Gallery" and gallery_images:
            content_str, err = _build_gallery_content(credentials, gallery_images)
            if err is not None:
                return err
            payload["content"] = content_str
        if post_type == "Web Story" and web_story_images:
            content_str, err = _build_web_story_content(credentials, web_story_images)
            if err is not None:
                return err
            payload["content"] = content_str

        # Featured image: store as the relative media path the dashboard's featured-image
        # widget reads (a bare media id renders publicly but stays blank in the editor).
        if payload.get("banner_url") is not None:
            resolved, err = _resolve_banner_url(credentials, payload["banner_url"])
            if err is not None:
                return err
            payload["banner_url"] = resolved

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
                    "Web Story posts require slides. Pass web_story_images as an array of "
                    "{img_src (media path) OR id (numeric media id), title, desc, alt_text}; "
                    "the tool serializes them into content.data.web_story (the image-slide shape the "
                    "dashboard and public page read — a real Web Story is image slides, NOT AMP markup). "
                    "Alternatively pass raw AMP story markup in the 'content' field. "
                    "meta_landscape_thumbnail is optional."
                ),
                "retryable": False,
            }
        if post_type == "Gallery" and not payload.get("content") and not payload.get("custom_entity"):
            return {
                "error_type": "missing_required_field",
                "message": (
                    "Gallery posts require slides. Pass gallery_images as an array of "
                    "{img_src (media path) OR id (numeric media id), title, desc, alt_text, caption_text}; "
                    "the tool serializes them into content.data.gallery (the shape the dashboard 'Gallery Slides' "
                    "editor and the public page both read). An empty gallery creates as a Draft but cannot be published."
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
            "MEDIA SOURCING for banner_url / gallery img_src: pass a relative Publive media path "
            "(e.g. 'odishatv/media/media_files/foo.jpg') or a numeric media id from "
            "list_media_assets/get_media_asset. Use register_media_asset ONLY for assets ALREADY hosted at a "
            "stable, permanent URL OUTSIDE Publive — it will NOT produce a usable img_src/banner_url path for "
            "files that need to live on Publive's own storage. "
            "Cannot be changed after creation: english_title, type, slug."
        ),
        inputSchema={
            "type": "object",
            "required": ["id"],
            "properties": {
                "id":                  {"type": "integer", "description": "Post ID"},
                "title":               {"type": "string",  "description": "New post headline"},
                "content":             {"type": "string",  "description": "New HTML body content. For Gallery posts prefer gallery_images; a raw content string must be JSON of {\"data\": {\"gallery\": [{\"type\": \"Image\", \"img_src\": \"<media path>\", \"title\": \"...\", \"desc\": \"...\", \"alt_text\": \"...\", \"caption_text\": null}]}} (the exact shape the dashboard writes — NO \"web_story\" key, NO top-level \"content_html\" unless you actually have body HTML)."},
                "gallery_images":      {"type": "array",   "description": "Gallery posts only — replacement slides, serialized into content.data.gallery (the shape the dashboard 'Gallery Slides' editor and the public page both read). Preferred over a raw content string. Each item: img_src (relative media path, or a full CDN URL which is normalized) OR id (numeric media id, resolved to the media path automatically); plus optional title, desc, alt_text, caption_text.",
                                        "items": {"type": "object", "properties": {
                                            "img_src":      {"type": "string",  "description": "Slide image — the relative media path the CMS stores (e.g. 'odishatv/media/media_files/foo.jpg'). A full CDN URL is also accepted and normalized to the path automatically."},
                                            "id":           {"type": "integer", "description": "Numeric media id (alternative to img_src; resolved to the media path automatically)."},
                                            "type":         {"type": "string",  "description": "Slide type — defaults to 'Image'."},
                                            "title":        {"type": "string",  "description": "Slide title."},
                                            "desc":         {"type": "string",  "description": "Slide description text."},
                                            "alt_text":     {"type": "string",  "description": "Image alt text."},
                                            "caption_text": {"type": "string",  "description": "Caption text. Omitted from the stored slide when empty."},
                                        }}},
                "web_story_images":    {"type": "array",   "description": "Web Story posts only — replacement image slides, serialized into content.data.web_story (the image-slide shape the dashboard and public page read; a real Web Story is image slides, NOT AMP markup). Preferred over a raw content string. Each item: img_src (relative media path, or a full CDN URL which is normalized) OR id (numeric media id, resolved to the media path automatically); plus optional title, desc, alt_text.",
                                        "items": {"type": "object", "properties": {
                                            "img_src":      {"type": "string",  "description": "Slide image — the relative media path the CMS stores (e.g. 'odishatv/media/post_attachments/uploadimage/library/16_9/16_9_0/foo.jpg'). A full CDN URL is also accepted and normalized."},
                                            "id":           {"type": "integer", "description": "Numeric media id (alternative to img_src; resolved to the media path automatically)."},
                                            "type":         {"type": "string",  "description": "Slide type — defaults to 'Image'."},
                                            "title":        {"type": "string",  "description": "Slide title."},
                                            "desc":         {"type": "string",  "description": "Slide description text."},
                                            "alt_text":     {"type": "string",  "description": "Image alt text."},
                                        }}},
                "status":              {"type": "string",  "description": "Draft, Published, Scheduled, or Approval Pending"},
                "primary_category":    {"type": "integer", "description": "New primary category ID"},
                "contributors":        {"type": "string",  "description": "Comma-separated author IDs"},
                "tags":                {"type": "string",  "description": "Comma-separated tag IDs"},
                "categories":          {"type": "string",  "description": "Comma-separated category IDs"},
                "banner_url":          {"type": ["integer", "string"], "description": "New featured image. Pass a numeric media id (resolved to its media path automatically), the relative media path, or a full CDN URL. Stored as the relative path the dashboard's featured-image widget reads."},
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

        # Gallery / Web Story: serialize structured image slides into content.data.gallery /
        # content.data.web_story (the blob the dashboard editor and public page read) before
        # the diff/patch. These helper arrays are never sent to the API as top-level fields.
        gallery_images   = changes.pop("gallery_images", None)
        web_story_images = changes.pop("web_story_images", None)
        if gallery_images:
            content_str, err = _build_gallery_content(credentials, gallery_images)
            if err is not None:
                return err
            changes["content"] = content_str
        if web_story_images:
            content_str, err = _build_web_story_content(credentials, web_story_images)
            if err is not None:
                return err
            changes["content"] = content_str

        # Featured image: store as the relative media path the dashboard widget reads.
        if changes.get("banner_url") is not None:
            resolved, err = _resolve_banner_url(credentials, changes["banner_url"])
            if err is not None:
                return err
            changes["banner_url"] = resolved

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
