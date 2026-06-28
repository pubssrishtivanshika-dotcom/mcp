"""Tool descriptions and JSON input schemas for the CMS post tools.

Kept separate from the handler logic (:mod:`.tools` / :mod:`.operations`) so the large
description strings and inputSchema dicts don't drown out the code. The slide-item
sub-schemas are shared between the create and update tools to avoid drift.
"""
from mcp.tool_registry import PAGINATION_PROPERTIES

# ── Shared slide-item sub-schemas (used by both create_post and update_post) ─────────────
GALLERY_SLIDE_ITEM = {
    "type": "object",
    "properties": {
        "img_src":      {"type": "string",  "description": "Slide image — the relative media path the CMS stores (e.g. 'odishatv/media/media_files/foo.jpg'). A full CDN URL is also accepted and normalized to the path automatically."},
        "id":           {"type": "integer", "description": "Numeric media id (alternative to img_src; resolved to the media path automatically)."},
        "type":         {"type": "string",  "description": "Slide type — defaults to 'Image'."},
        "title":        {"type": "string",  "description": "Slide title."},
        "desc":         {"type": "string",  "description": "Slide description text."},
        "alt_text":     {"type": "string",  "description": "Image alt text."},
        "caption_text": {"type": "string",  "description": "Caption text. Omitted from the stored slide when empty."},
    },
}
WEB_STORY_SLIDE_ITEM = {
    "type": "object",
    "properties": {
        "img_src":  {"type": "string",  "description": "Slide image — the relative media path the CMS stores (e.g. 'odishatv/media/post_attachments/uploadimage/library/16_9/16_9_0/foo.jpg'). A full CDN URL is also accepted and normalized."},
        "id":       {"type": "integer", "description": "Numeric media id (alternative to img_src; resolved to the media path automatically)."},
        "type":     {"type": "string",  "description": "Slide type — defaults to 'Image'."},
        "title":    {"type": "string",  "description": "Slide title."},
        "desc":     {"type": "string",  "description": "Slide description text."},
        "alt_text": {"type": "string",  "description": "Image alt text."},
    },
}


# ── list_editorial_posts ────────────────────────────────────────────────────────────────
LIST_DESCRIPTION = (
    "List all CMS posts with pagination. Includes drafts, published, and scheduled posts. "
    "NOTE: if the user only needs published posts, prefer the CDS fetch_published_posts tool. "
    "Returns results directly — no confirmation step needed."
)
LIST_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        **PAGINATION_PROPERTIES,
    },
}


# ── get_editorial_post ──────────────────────────────────────────────────────────────────
GET_DESCRIPTION = (
    "Retrieve a single CMS post by ID. Returns full details including draft and scheduled content. "
    "NOTE: if the user only needs basic published data, prefer the CDS fetch_published_post tool. "
    "Returns results directly — no confirmation step needed."
)
GET_INPUT_SCHEMA = {
    "type": "object",
    "required": ["id"],
    "properties": {"id": {"type": "integer", "description": "Post ID"}},
}


# ── create_post ─────────────────────────────────────────────────────────────────────────
CREATE_DESCRIPTION = (
    "Create a new post in the CMS. "
    "BEFORE calling: you MUST have all six required fields — title, english_title, type, status, "
    "primary_category, AND contributors (at least one author ID). "
    "contributors is REQUIRED by the API — omitting it causes a hard validation failure. "
    "If the user has not provided an author ID, call fetch_authors first to get one, then ask the user to confirm. "
    "english_title must be plain English text matching the title, NOT a pre-slugified string. "
    "TYPE-SPECIFIC REQUIREMENTS — do NOT attempt to create these without the noted fields: "
    "Video (non-Draft): follows the dashboard journey. The USER chooses primary_category, "
    "contributors, content, tags, banner_url (the custom thumbnail — an IMAGE media id), and "
    "meta_video_url (the Featured Video URL — a YouTube/Vimeo/media link; the <iframe> embed is "
    "built from it automatically, so you do NOT need to pass meta_video_embed). The USER also "
    "provides summary and short_description (offer to draft these from the content). The AI fills "
    "banner_description (the featured-video caption), categories (optional, strong match only), and "
    "seo_keyphrase when the user didn't set them. If a user field "
    "is missing the tool returns a friendly needs_input checklist (NOT an error). Same length rules "
    "as Article (title >= 10, english_title <= 250). You may still pass meta_video_embed directly "
    "instead of a URL. Draft Videos still hard-require a video source. "
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
    "Article (non-Draft): follows the dashboard 'Post Content' journey. The USER chooses "
    "primary_category, contributors, content (the editor body), tags, banner_url, "
    "short_description, and summary; if any are missing the tool returns a friendly "
    "needs_input checklist (NOT an error) — collect those from the user, then call again. "
    "The AI fills categories (only on a strong match), seo_keyphrase, and banner_description "
    "(derived from the media asset) when the user didn't set them. Length rules: title >= 10 "
    "characters, english_title <= 250 characters. "
    "LiveBlog, CustomPage: no extra required fields beyond the six standard ones. "
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
)
CREATE_INPUT_SCHEMA = {
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
                                "items": GALLERY_SLIDE_ITEM},
        "web_story_images":    {"type": "array",   "description": "Web Story posts only — image slides, serialized into content.data.web_story (the image-slide shape the dashboard and public page read; a real Web Story is image slides, NOT AMP markup). Preferred over a raw content string. Each item: img_src (relative media path, or a full CDN URL which is normalized) OR id (numeric media id, resolved to the media path automatically); plus optional title, desc, alt_text.",
                                "items": WEB_STORY_SLIDE_ITEM},
        "tags":                {"type": "string",  "description": "Comma-separated tag IDs"},
        "categories":          {"type": "string",  "description": "Comma-separated additional category IDs"},
        "banner_url":          {"type": ["integer", "string"], "description": "Featured image — the numeric media-library object id (the 'id' from get_media_asset / list_media_assets). The CMS stores this as the media object id, NOT a path or URL; passing a path/URL is rejected with 'Banner URL must be a valid media object ID'."},
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
}


# ── update_post ─────────────────────────────────────────────────────────────────────────
UPDATE_DESCRIPTION = (
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
)
UPDATE_INPUT_SCHEMA = {
    "type": "object",
    "required": ["id"],
    "properties": {
        "id":                  {"type": "integer", "description": "Post ID"},
        "title":               {"type": "string",  "description": "New post headline"},
        "content":             {"type": "string",  "description": "New HTML body content. For Gallery posts prefer gallery_images; a raw content string must be JSON of {\"data\": {\"gallery\": [{\"type\": \"Image\", \"img_src\": \"<media path>\", \"title\": \"...\", \"desc\": \"...\", \"alt_text\": \"...\", \"caption_text\": null}]}} (the exact shape the dashboard writes — NO \"web_story\" key, NO top-level \"content_html\" unless you actually have body HTML)."},
        "gallery_images":      {"type": "array",   "description": "Gallery posts only — replacement slides, serialized into content.data.gallery (the shape the dashboard 'Gallery Slides' editor and the public page both read). Preferred over a raw content string. Each item: img_src (relative media path, or a full CDN URL which is normalized) OR id (numeric media id, resolved to the media path automatically); plus optional title, desc, alt_text, caption_text.",
                                "items": GALLERY_SLIDE_ITEM},
        "web_story_images":    {"type": "array",   "description": "Web Story posts only — replacement image slides, serialized into content.data.web_story (the image-slide shape the dashboard and public page read; a real Web Story is image slides, NOT AMP markup). Preferred over a raw content string. Each item: img_src (relative media path, or a full CDN URL which is normalized) OR id (numeric media id, resolved to the media path automatically); plus optional title, desc, alt_text.",
                                "items": WEB_STORY_SLIDE_ITEM},
        "status":              {"type": "string",  "description": "Draft, Published, Scheduled, or Approval Pending"},
        "primary_category":    {"type": "integer", "description": "New primary category ID"},
        "contributors":        {"type": "string",  "description": "Comma-separated author IDs"},
        "tags":                {"type": "string",  "description": "Comma-separated tag IDs"},
        "categories":          {"type": "string",  "description": "Comma-separated category IDs"},
        "banner_url":          {"type": ["integer", "string"], "description": "New featured image — the numeric media-library object id (the 'id' from get_media_asset / list_media_assets). The CMS stores this as the media object id, NOT a path or URL; passing a path/URL is rejected with 'Banner URL must be a valid media object ID'."},
        "short_description":   {"type": "string",  "description": "New SEO meta description"},
        "hide_banner_image":   {"type": "boolean", "description": "Hide the featured image"},
        "custom_published_at": {"type": "string",  "description": "Backdated publish timestamp ISO 8601"},
        "scheduled_at":        {"type": "string",  "description": "Future publish datetime, format 'YYYY-MM-DD HH:MM:SS' (NOT ISO 8601 with T/Z)"},
        "dry_run":             {"type": "boolean", "description": "true = show diff only, no changes (default); false = apply update"},
        "confirm_publish":     {"type": "boolean", "description": "Must be true when setting status=Published with dry_run=false."},
    },
}


# ── delete_post ─────────────────────────────────────────────────────────────────────────
DELETE_DESCRIPTION = (
    "Permanently delete a post and all its associated data. This action CANNOT be undone. "
    "Workflow: dry_run=true (default) shows full post details — no deletion. "
    "Once confirmed, call again with dry_run=false AND confirm_delete=true."
)
DELETE_INPUT_SCHEMA = {
    "type": "object",
    "required": ["id"],
    "properties": {
        "id":             {"type": "integer", "description": "Post ID"},
        "dry_run":        {"type": "boolean", "description": "true = preview only (default); false = delete (also requires confirm_delete=true)"},
        "confirm_delete": {"type": "boolean", "description": "Must be explicitly set to true — together with dry_run=false — to execute the deletion"},
    },
}
