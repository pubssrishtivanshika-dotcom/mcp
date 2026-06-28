# Responsibility: URL routing for OAuth 2.0 PKCE flow and session-based auth.
from django.urls import path

from authentication import views

urlpatterns = [
   
    # OAuth discovery (well-known endpoints)
    path(".well-known/oauth-protected-resource", views.OAuthProtectedResourceView.as_view(), name="oauth-protected-resource"),
    path(".well-known/oauth-protected-resource/<path:resource_path>", views.OAuthProtectedResourceView.as_view(), name="oauth-protected-resource-path"),
    path(".well-known/oauth-authorization-server", views.OAuthServerMetadataView.as_view(), name="oauth-server-metadata"),
    path(".well-known/openid-configuration", views.OAuthServerMetadataView.as_view(), name="openid-configuration"),
   
    # OAuth 2.0 PKCE flow (Claude Desktop, Cursor, ChatGPT, Anthropic SDK)
    path("register", views.OAuthRegisterView.as_view(), name="oauth-register"),
    path("authorize", views.OAuthAuthorizeView.as_view(), name="oauth-authorize-root"),
    path("oauth/authorize", views.OAuthAuthorizeView.as_view(), name="oauth-authorize"),
    path("token", views.OAuthTokenView.as_view(), name="oauth-token-root"),
    path("oauth/token", views.OAuthTokenView.as_view(), name="oauth-token"),
    path("revoke", views.OAuthRevokeView.as_view(), name="oauth-revoke"),
    path("oauth/revoke", views.OAuthRevokeView.as_view(), name="oauth-revoke-prefixed"),
    path("userinfo", views.OAuthUserInfoView.as_view(), name="oauth-userinfo"),
   
    # Session-based auth (human browser users)
    path("connect", views.ConnectView.as_view(), name="connect"),
    path("auth/login", views.AuthLoginView.as_view(), name="auth_login"),
    path("auth/success", views.AuthSuccessView.as_view(), name="auth_success"),
    path("auth/status", views.AuthStatusView.as_view(), name="auth_status"),
    path("auth/logout", views.AuthLogoutView.as_view(), name="auth_logout"),

    # Browser media gallery (session-authenticated)
    path("media", views.MediaGalleryView.as_view(), name="media_gallery"),
    path("media/assets", views.MediaAssetsView.as_view(), name="media_assets"),
]
