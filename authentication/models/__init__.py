# Responsibility: Auth data models — OAuth 2.0 PKCE flow + CORS allowlist.
# Re-exports every model/manager so `from authentication.models import X` keeps working
# and Django can discover the models for this app.
from __future__ import annotations

from authentication.models.client import OAuthClient, OAuthClientManager
from authentication.models.code import OAuthCode, OAuthCodeManager
from authentication.models.origin import AllowedOrigin
from authentication.models.token import OAuthToken, OAuthTokenManager

__all__ = [
    "OAuthClient",
    "OAuthClientManager",
    "OAuthCode",
    "OAuthCodeManager",
    "AllowedOrigin",
    "OAuthToken",
    "OAuthTokenManager",
]
