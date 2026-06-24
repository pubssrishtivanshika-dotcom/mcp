# Responsibility: Shared helpers for the auth view handlers (token expiry, error/success responses).
import logging
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone

logger = logging.getLogger(__name__)


def _access_token_expiry():
    """Return the absolute expiry timestamp for a freshly issued access token."""
    return timezone.now() + timedelta(seconds=settings.OAUTH_ACCESS_TOKEN_TTL_SECONDS)


def _auth_failure(
    *, error: str, status: int, description: Optional[str] = None,
    log: Optional[str] = None, log_args: tuple = (), log_level: str = "warning",
    exc_info=None,
) -> JsonResponse:
    """Log the auth failure and return the standard error response."""
    if log:
        getattr(logger, log_level)(log, *log_args, exc_info=exc_info)

    body = {"error": error}
    if description is not None:
        body["error_description"] = description

    return JsonResponse(body, status=status)


def _token_response(access_token: str, refresh_token: str) -> JsonResponse:
    """    Build the standard OAuth bearer-token success response.   """

    return JsonResponse({
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.OAUTH_ACCESS_TOKEN_TTL_SECONDS,
        "refresh_token": refresh_token,
    })
