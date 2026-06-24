# Responsibility: Compose the auth service from its focused mixins and expose the shared singleton.
#
# The business-logic helpers for the OAuth / session auth flows are split across
# focused mixin modules in this package. They are composed here into a single
# AuthService class so existing imports (e.g. `from authentication.services import
# auth_service`) keep working.
from authentication.services.base import CredentialCheck
from authentication.services.credentials import CredentialsMixin
from authentication.services.origins import OriginMixin
from authentication.services.redirect_uris import RedirectUriMixin
from authentication.services.sessions import SessionMixin
from authentication.services.token_body import TokenBodyMixin


class AuthService(
    SessionMixin,
    OriginMixin,
    RedirectUriMixin,
    TokenBodyMixin,
    CredentialsMixin,
):
    """Business-logic helpers for the OAuth / session auth flows."""


# Module-level singleton — the shared auth service object.
auth_service = AuthService()

__all__ = ["AuthService", "CredentialCheck", "auth_service"]
