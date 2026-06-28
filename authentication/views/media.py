# Responsibility: Browser-facing media gallery page + JSON proxy over the
# list_media_assets CMS tool (session-authenticated).
import logging

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views import View

from authentication.services import auth_service
from mcp.clients.cms import cms_client

logger = logging.getLogger(__name__)

_MEDIA_PATH = "/media-library/"
# Only the fields the gallery renders — keeps the payload small and stable.
_ASSET_FIELDS = ("id", "filename", "alt_text", "caption", "path", "source", "type", "date")


def _normalize_assets(payload) -> list:
    """Pull the asset list out of whatever envelope the CMS returns and project
    it down to the fields the gallery needs."""
    if isinstance(payload, dict):
        items = payload.get("data") or payload.get("results") or payload.get("items") or []
    elif isinstance(payload, list):
        items = payload
    else:
        items = []

    assets = []
    for item in items:
        if not isinstance(item, dict):
            continue
        assets.append({k: item.get(k) for k in _ASSET_FIELDS})
    return assets


class MediaGalleryView(View):
    """Render the media gallery page; redirect to /connect if not signed in."""

    def get(self, request: HttpRequest) -> HttpResponse:
        if not auth_service.get_session_credentials(request.session):
            return redirect("/connect")
        return render(request, "gallery.html")


class MediaAssetsView(View):
    """Return a page of media assets as JSON for the gallery front-end."""

    def get(self, request: HttpRequest) -> JsonResponse:
        credentials = auth_service.get_session_credentials(request.session)
        if not credentials:
            return JsonResponse({"error": "Not authenticated."}, status=401)

        try:
            page = int(request.GET.get("page", 1))
            limit = int(request.GET.get("limit", 24))
        except (TypeError, ValueError):
            page, limit = 1, 24

        result = cms_client.get(credentials, _MEDIA_PATH, {"page": page, "limit": limit})
        if isinstance(result, dict) and "error_type" in result:
            status = 401 if result.get("error_type") == "auth_error" else 502
            logger.warning("media_assets: CMS error type=%s", result.get("error_type"))
            return JsonResponse({"error": result.get("message", "Upstream error.")}, status=status)

        return JsonResponse({"page": page, "limit": limit, "assets": _normalize_assets(result)})
