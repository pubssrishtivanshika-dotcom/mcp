# Responsibility: OAuth 2.0 discovery endpoints (protected-resource and authorization-server metadata).
from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views import View


class OAuthProtectedResourceView(View):
    """Serve the OAuth 2.0 protected-resource metadata document (RFC 9728)."""

    def get(self, request: HttpRequest, resource_path: str = "") -> JsonResponse:
        base_url = settings.BASE_URL.rstrip("/")
        return JsonResponse({
            "resource": f"{base_url}/mcp",
            "authorization_servers": [base_url],
        })


class OAuthServerMetadataView(View):
    """Serve the OAuth 2.0 / OpenID Connect authorization server metadata document."""

    def get(self, request: HttpRequest) -> JsonResponse:
        base_url = settings.BASE_URL.rstrip("/")
        return JsonResponse({
            "issuer": base_url,
            "authorization_endpoint": f"{base_url}/authorize",
            "token_endpoint": f"{base_url}/token",
            "revocation_endpoint": f"{base_url}/revoke",
            "registration_endpoint": f"{base_url}/register",
            "userinfo_endpoint": f"{base_url}/userinfo",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
            "revocation_endpoint_auth_methods_supported": ["none"],
            "scopes_supported": ["read", "write"],
        })
