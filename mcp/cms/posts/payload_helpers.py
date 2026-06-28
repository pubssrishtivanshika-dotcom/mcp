"""Payload normalization and upstream-error remapping for post tools — int coercion,
list-bracket stripping, type-validation error translation, and create-retry helpers."""
import contextlib

from mcp.clients.cms import cms_client


def _coerce_post_int_fields(payload: dict) -> None:
    # banner_url is the integer media-library object id the CMS's featured-image field
    # requires (resolved/validated upstream by _resolve_banner_url, which already returns an
    # int); listed here so a digit-string id passed straight through is also coerced.
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
