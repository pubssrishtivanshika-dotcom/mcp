"""Thumbnail URL building and parallel base64 fetching for rich media responses."""
import base64
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests as _requests

logger = logging.getLogger(__name__)

_THUMBOR_BASE = "https://cds-beta.thepublive.com"
_THUMB_WIDTH  = 200


def thumbnail_url(path: str) -> str:
    """Return a Thumbor preview URL for a storage key, or the path as-is for external URLs."""
    if not path:
        return ""
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return f"{_THUMBOR_BASE}/unsafe/fit-in/{_THUMB_WIDTH}x0/{path}"


def _fetch_one(url: str) -> tuple[str | None, str]:
    """Fetch a single image URL; return (base64_data, mime_type) or (None, '') on failure."""
    try:
        r = _requests.get(url, timeout=4)
        content_type = r.headers.get("content-type", "")
        if r.ok and content_type.startswith("image/"):
            mime = content_type.split(";")[0].strip()
            return base64.b64encode(r.content).decode(), mime
    except Exception:
        logger.debug("thumbnail fetch failed: url=%s", url, exc_info=True)
    return None, ""


def fetch_thumbnails(items: list[dict]) -> list[dict]:
    """Fetch base64 thumbnails for a list of media items in parallel.

    Each item must have a 'thumbnail_url' key. Returns the same list with
    '_b64' and '_mime' keys added (both empty string on failure).
    """
    def fetch(item):
        b64, mime = _fetch_one(item.get("thumbnail_url", ""))
        return {**item, "_b64": b64 or "", "_mime": mime}

    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(fetch, items))
    return results


def build_rich_media_response(raw_items: list[dict], meta: dict | None = None) -> dict:
    """Wrap a list of raw CMS media records into the _mcp_rich envelope.

    Filters to Image-type assets only for thumbnail rendering; non-Image assets
    are included in the envelope but won't get an inline image block in dispatch.
    """
    items = []
    for item in raw_items:
        path = item.get("path") or item.get("absolute_path") or ""
        items.append({
            "id":            item.get("id"),
            "filename":      item.get("filename"),
            "path":          path,
            "alt_text":      item.get("alt_text") or "",
            "type":          item.get("type"),
            "caption":       item.get("caption") or "",
            "source":        item.get("source") or "",
            "meta_data":     item.get("meta_data"),
            "thumbnail_url": thumbnail_url(path) if item.get("type") in (None, "Image") else "",
        })
    return {"_mcp_rich": True, "items": items, "meta": meta or {}}
