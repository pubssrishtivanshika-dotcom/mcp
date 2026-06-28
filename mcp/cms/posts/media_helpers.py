"""Media/image helpers for post tools — resolving media ids, normalizing image
paths, and serializing Gallery / Web Story image slides into the content blob the
CMS dashboard editor and public page read."""
import json
import re

from mcp.clients.cms import cms_client


# A Thumbor dimension segment, e.g. '750x500' / '0x500' / '-100x100' (negative = flip).
_THUMBOR_DIM_SEG = re.compile(r"^-?\d+x-?\d+$")


def _normalize_img_src(value):
    """Reduce a media reference to the bare relative storage key the CMS gallery stores"""
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
    """Resolve a CMS media-library id to the storage path the gallery stores  """
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
    # Prefer the relative 'path' (the storage key the writer expects); fall back to absolute_path (a full CDN URL) which callers normalize back down to the relative key.
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
    """Build a caller-facing error that surfaces the REAL underlying CMS failure """
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
    two share an identical slide structure. """
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
    """Resolve a featured-image reference to the media-library object ID the CMS's
    banner_url field requires. The CMS stores banner_url as the integer media object id —
    it rejects a path or URL with 'Banner URL must be a valid media object ID'. We accept a
    numeric id (validated against the media library so a wrong id surfaces the REAL cause —
    a wrong id vs. an auth/permission/timeout failure — instead of that opaque rejection)
    and return it as an int. Returns (resolved, error); exactly one is non-None.
    """
    if isinstance(value, int) or (isinstance(value, str) and value.strip().isdigit()):
        media_id = int(value)
        _, err = _resolve_media_url(credentials, media_id)  # existence/permission check only
        if err is not None:
            return None, _resolve_media_error_message(
                "Featured image (banner_url) could not be set:",
                media_id,
                err,
                "banner_url must be a numeric media object id — get it from "
                "get_media_asset / list_media_assets (the 'id' field).",
            )
        return media_id, None
    # The CMS banner_url field only accepts a media object id; a path/URL string is rejected
    # upstream as 'must be a valid media object ID', so we reject it here with a clear cause.
    return None, {
        "error_type": "bad_request",
        "message": (
            "banner_url must be a numeric media object id (the 'id' from "
            "get_media_asset / list_media_assets), not a path or URL."
        ),
        "retryable": False,
    }
