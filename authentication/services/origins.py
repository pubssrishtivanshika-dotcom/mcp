# Responsibility: Browser Origin allowlisting for OAuth/session requests.
import logging
from typing import Optional

from django.conf import settings
from django.http import HttpRequest, JsonResponse

logger = logging.getLogger(__name__)


class OriginMixin:
    """Origin-header validation helpers for the auth service."""

    def get_allowed_origins(self) -> set[str]:
        """Return the set of permitted browser Origins (normalized, no trailing slash).

        The authentication.AllowedOrigin table is the single source of truth, read directly
        from the DB on every call. The table is seeded by data migration authentication
        0002_seed_allowed_origins and managed at runtime in the DB. On a DB error the result is left empty
        so check_origin fails closed (browser Origins blocked); Origin-less desktop
        clients and same-origin BASE_URL requests are unaffected.
        """
        try:
            from authentication.models import AllowedOrigin   # legitimate lazy import to avoid a circular models ↔ services dependency, not a redundancy

            return {
                o.rstrip("/")
                for o in AllowedOrigin.objects.filter(is_active=True).values_list(
                    "origin", flat=True
                )
            }
        except Exception:  # table missing / DB error — fail closed
            logger.warning("OAuth: could not load AllowedOrigin from DB; blocking browser origins this request")
            return set()

    def check_origin(self, request: HttpRequest) -> Optional[JsonResponse]:
        """Return None if the Origin header is acceptable; return a 403 JsonResponse otherwise.

        Desktop MCP clients (Claude Desktop, Cursor) do not send an Origin header because
        they are not browsers — those are unconditionally allowed. When an Origin IS present
        (web-based Claude clients), it must appear in the AllowedOrigin table (see
        get_allowed_origins).
        """
        origin: str = request.META.get("HTTP_ORIGIN", "").rstrip("/")
        if not origin:
            return None

        allowed = set(self.get_allowed_origins())
        allowed.add(settings.BASE_URL.rstrip("/"))  # always allow same-origin

        if origin in allowed:
            return None

        logger.warning("OAuth: blocked request from disallowed origin=%r", origin)
        return JsonResponse(
            {"error": "invalid_origin", "error_description": "Origin not allowed"},
            status=403,
        )
