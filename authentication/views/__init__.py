# Responsibility: Aggregate the auth view handlers into a single `authentication.views` namespace.
#
# The view handlers for the OAuth 2.0 PKCE flow and session-based auth are split
# across focused modules in this package. They are re-exported here so existing
# imports (e.g. `from authentication import views; views.OAuthTokenView`) keep working.
from authentication.views.authorize import OAuthAuthorizeView
from authentication.views.discovery import (
    OAuthProtectedResourceView,
    OAuthServerMetadataView,
)
from authentication.views.registration import OAuthRegisterView
from authentication.views.revoke import OAuthRevokeView
from authentication.views.session import (
    AuthLoginView,
    AuthLogoutView,
    AuthStatusView,
    AuthSuccessView,
    ConnectView,
)
from authentication.views.token import OAuthTokenView
from authentication.views.userinfo import OAuthUserInfoView

__all__ = [
    "OAuthProtectedResourceView",
    "OAuthServerMetadataView",
    "OAuthRegisterView",
    "OAuthAuthorizeView",
    "OAuthTokenView",
    "OAuthRevokeView",
    "OAuthUserInfoView",
    "ConnectView",
    "AuthLoginView",
    "AuthSuccessView",
    "AuthStatusView",
    "AuthLogoutView",
]
