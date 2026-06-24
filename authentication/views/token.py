# Responsibility: OAuth 2.0 token endpoint (authorization_code and refresh_token grants).
import base64
import hashlib
import logging
import secrets
from typing import Optional

from django.db import transaction
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from authentication.models import OAuthCode, OAuthToken
from authentication.services import auth_service
from authentication.views.helpers import _access_token_expiry, _auth_failure, _token_response

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class OAuthTokenView(View):
    """Issue or refresh a bearer token; supports authorization_code and refresh_token grants."""

    def post(self, request: HttpRequest) -> JsonResponse:
        data, parse_err = auth_service.parse_oauth_token_body(request)
        if parse_err:
            logger.warning("OAuth token: invalid request body content-type=%s", request.content_type)
            return parse_err

        origin_err: Optional[JsonResponse] = auth_service.check_origin(request)
        if origin_err:
            return origin_err

        grant_type: str = data.get("grant_type", "")
        if grant_type == "implicit":
            return _auth_failure(
                error="unsupported_grant_type",
                description="Implicit grant is not supported", status=400,
                log="OAuth token: rejected implicit grant",
            )

        try:
            # ── Refresh token grant ───────────────────────────────────────────────
            if grant_type == "refresh_token":
                refresh_val: str = data.get("refresh_token", "")
                new_access: str  = secrets.token_urlsafe(32)
                new_refresh: str = secrets.token_urlsafe(32)
                new_expires_at   = _access_token_expiry()

                with transaction.atomic():
                    existing = OAuthToken.objects.get_for_update_by_refresh_token(refresh_val)
                    if existing is None:
                        return _auth_failure(
                            error="invalid_grant",
                            description="Unknown refresh token", status=400,
                            log="OAuth token: unknown refresh_token",
                        )

                    client_id = existing.client_id
                    publisher_id = existing.publisher_id
                    existing.token = new_access
                    existing.refresh_token = new_refresh
                    existing.expires_at = new_expires_at
                    existing.save(update_fields=["token", "refresh_token", "expires_at"])

                logger.info("OAuth token refreshed: publisher=%s client=%s", publisher_id, client_id)
                return _token_response(new_access, new_refresh)

            # ── Authorization code grant ──────────────────────────────────────────
            if grant_type != "authorization_code":
                return _auth_failure(
                    error="unsupported_grant_type", status=400,
                    log="OAuth token: unsupported grant_type=%s client=%s", log_args=(grant_type, data.get("client_id")),
                )

            code: str          = data.get("code", "")
            code_verifier: str = data.get("code_verifier", "")

            auth_code = OAuthCode.objects.get_by_code(code)
            if auth_code is None:
                return _auth_failure(
                    error="invalid_grant",
                    description="Unknown code", status=400,
                    log="OAuth token: unknown code client=%s", log_args=(data.get("client_id"),),
                )

            if auth_code.expires_at < timezone.now():
                auth_code.delete()
                return _auth_failure(
                    error="invalid_grant",
                    description="Code expired", status=400,
                    log="OAuth token: expired code client=%s", log_args=(data.get("client_id"),),
                )

            expected: str = base64.urlsafe_b64encode(
                hashlib.sha256(code_verifier.encode()).digest()
            ).rstrip(b"=").decode()
            if expected != auth_code.code_challenge:
                return _auth_failure(
                    error="invalid_grant",
                    description="PKCE verification failed", status=400,
                    log="OAuth token: PKCE verification failed client=%s", log_args=(data.get("client_id"),),
                )

            token_redirect_uri: str = data.get("redirect_uri", "")
            if auth_code.redirect_uri and token_redirect_uri != auth_code.redirect_uri:
                return _auth_failure(
                    error="invalid_grant",
                    description="redirect_uri mismatch", status=400,
                    log="OAuth token: redirect_uri mismatch client=%s", log_args=(data.get("client_id"),),
                )

            credentials: dict    = auth_code.credentials
            oauth_client_id: str = data.get("client_id") or auth_code.client_id
            publisher_id         = credentials.get("publisherId", "")
            token_credentials    = {k: v for k, v in credentials.items() if k != "publisherId"}
            auth_code.delete()

            existing = OAuthToken.objects.get_active_token(oauth_client_id, publisher_id)

            if existing:
                update_fields = ["expires_at", "credentials"]
                existing.expires_at = _access_token_expiry()
                existing.credentials = token_credentials
                if not existing.refresh_token:
                    existing.refresh_token = secrets.token_urlsafe(32)
                    update_fields.append("refresh_token")
                existing.save(update_fields=update_fields)
                logger.info(
                    "OAuth token reused (stable): publisher=%s client=%s",
                    publisher_id, oauth_client_id,
                )
                return _token_response(existing.token, existing.refresh_token)

            token: str       = secrets.token_urlsafe(32)
            new_refresh: str = secrets.token_urlsafe(32)
            OAuthToken.objects.create_token(
                token=token,
                client_id=oauth_client_id,
                publisher_id=publisher_id,
                refresh_token=new_refresh,
                credentials=token_credentials,
                expires_at=_access_token_expiry(),
            )

            logger.info("OAuth token issued (new): publisher=%s client=%s", publisher_id, oauth_client_id)
            return _token_response(token, new_refresh)
        except Exception:
            logger.error("OAuth token: unhandled error", exc_info=True)
            raise
