"""CORS origin checking, backed by the authentication.AllowedOrigin table.

django-cors-headers has no built-in way to source its allowlist from the
database, so we hook its `check_request_enabled` signal: for every incoming
request it asks "is this Origin allowed?" and we answer using the same
AuthService.get_allowed_origins() the OAuth endpoints already use, keeping
AllowedOrigin as the single source of truth.
"""
from __future__ import annotations

from django.http import HttpRequest
from corsheaders.signals import check_request_enabled
from authentication.services import auth_service


def _is_origin_allowed(sender, request: HttpRequest, **kwargs) -> bool:
    origin = request.META.get("HTTP_ORIGIN", "").rstrip("/")
    if not origin:
        return False
    return origin in auth_service.get_allowed_origins()


def register_cors_signal() -> None:
    check_request_enabled.connect(_is_origin_allowed)