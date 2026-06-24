# Responsibility: OIDC-style UserInfo endpoint resolving identity claims for the caller.
from django.http import HttpRequest, JsonResponse
from django.views import View

from mcp.protocol.auth import build_unauthorized_response, resolve_credentials


class OAuthUserInfoView(View):
    """Return identity claims for the caller resolved from their Bearer token or session.

    Mirrors the OpenID Connect UserInfo endpoint so any OAuth-aware MCP client can
    discover "who am I" via standard discovery (advertised as userinfo_endpoint in
    oauth_server_metadata) instead of guessing from tool results. `sub` is the
    stable subject identifier — here, the delegated Publive publisher ID, since
    Publive credentials are issued per-publisher rather than per individual user.
    """

    def get(self, request: HttpRequest) -> JsonResponse:
        credentials, _, error_code = resolve_credentials(request)
        if not credentials:
            return build_unauthorized_response(request, error_code)

        publisher_id: str = credentials.get("publisherId", "")
        return JsonResponse({
            "sub": publisher_id,
            "publisher_id": publisher_id,
        })
