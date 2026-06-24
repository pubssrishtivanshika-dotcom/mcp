# Responsibility: OAuth 2.0 token revocation endpoint (RFC 7009).
import logging

from django.http import HttpRequest, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from authentication.models import OAuthToken
from authentication.services import auth_service

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class OAuthRevokeView(View):
    """Revoke a bearer access token or refresh token (RFC 7009).

    Always returns HTTP 200 — per spec, the server must not reveal whether
    the token existed. Both access tokens and refresh tokens are accepted.
    """

    def post(self, request: HttpRequest) -> JsonResponse:
        data, parse_err = auth_service.parse_oauth_token_body(request)
        if parse_err:
            # Still return 200 per RFC 7009 § 2.2 — invalid requests are silently ignored
            return JsonResponse({})

        token_value: str = data.get("token", "").strip()
        hint: str = data.get("token_type_hint", "").strip()

        if not token_value:
            return JsonResponse({})

        revoked = False
        try:
            revoked = OAuthToken.objects.revoke(
                token_value, prefer_refresh=(hint == "refresh_token")
            )
        except Exception:
            logger.error("oauth_revoke: unexpected error", exc_info=True)
            # Still return 200 per spec
            return JsonResponse({})

        if revoked:
            logger.info("oauth_revoke: token revoked hint=%s", hint or "access_token")
        else:
            logger.info("oauth_revoke: token not found (already expired or invalid) hint=%s", hint or "access_token")

        return JsonResponse({})
