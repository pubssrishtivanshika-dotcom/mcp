# Responsibility: OAuth 2.0 authorization endpoint (credential form + auth-code issuance).
import logging
import secrets
from datetime import timedelta
from typing import Optional
from urllib.parse import urlencode

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views import View

from authentication.models import OAuthClient, OAuthCode
from authentication.services import auth_service

logger = logging.getLogger(__name__)

_IMPLICIT_RESPONSE_TYPES = frozenset({"token", "id_token token", "code token", "code id_token token"})


def _oauth_authorize_error(
    request: HttpRequest,
    *,
    error: str,
    description: str,
    status: int = 400,
) -> HttpResponse:
    """Return an OAuth error for browser-based authorize requests."""
    if request.method == "GET":
        return render(request, "authorize.html", {
            "client_id": request.GET.get("client_id", ""),
            "redirect_uri": request.GET.get("redirect_uri", ""),
            "state": request.GET.get("state", ""),
            "code_challenge": request.GET.get("code_challenge", ""),
            "code_challenge_method": request.GET.get("code_challenge_method", "S256"),
            "error": description,
        }, status=status)
    return JsonResponse({"error": error, "error_description": description}, status=status)


def _validate_authorize_request(
    client_id: Optional[str],
    redirect_uri: str,
    response_type: str,
) -> Optional[tuple[str, str]]:
    """Return (error, description) when the authorize request is invalid; else None."""
    if response_type in _IMPLICIT_RESPONSE_TYPES:
        return "unsupported_response_type", "Implicit grant is not supported"
    if response_type != "code":
        return "unsupported_response_type", "Only response_type=code is supported"

    if not client_id:
        return "invalid_request", "client_id is required"
    oauth_client = OAuthClient.objects.get_by_client_id(client_id)
    if oauth_client is None:
        return "invalid_client", "Unknown client_id"

    registered_uri: str = oauth_client.redirect_uri or ""
    if not registered_uri:
        return "invalid_request", "Client has no registered redirect URI"
    if not redirect_uri:
        return "invalid_request", "redirect_uri is required"
    if not auth_service.redirect_uris_match(redirect_uri, registered_uri):
        return "invalid_request", "redirect_uri does not match the registered value"

    return None


class OAuthAuthorizeView(View):
    """Show the authorization form (GET) or process credential submission and issue an auth code (POST)."""

    def get(self, request: HttpRequest) -> HttpResponse:
        response_type: str = request.GET.get("response_type", "code")
        client_id: str = request.GET.get("client_id", "")
        redirect_uri: str = request.GET.get("redirect_uri", "")
        auth_err = _validate_authorize_request(client_id or None, redirect_uri, response_type)
        if auth_err:
            error_code, description = auth_err
            return _oauth_authorize_error(
                request, error=error_code, description=description,
            )
        return render(request, "authorize.html", {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": request.GET.get("state", ""),
            "code_challenge": request.GET.get("code_challenge", ""),
            "code_challenge_method": request.GET.get("code_challenge_method", "S256"),
        })

    def post(self, request: HttpRequest) -> HttpResponse:
        client_id: Optional[str] = request.POST.get("client_id")

        publisher_id: str          = request.POST.get("publisherId", "").strip()
        api_key: str               = request.POST.get("apiKey", "").strip()
        api_secret: str            = request.POST.get("apiSecret", "").strip()
        redirect_uri: str          = request.POST.get("redirect_uri", "")
        state: str                 = request.POST.get("state", "")
        code_challenge: str        = request.POST.get("code_challenge", "")
        code_challenge_method: str = request.POST.get("code_challenge_method", "S256")

        ctx: dict = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "publisherId": publisher_id,
            "apiKey": api_key,
        }

        try:
            auth_err = _validate_authorize_request(client_id, redirect_uri, "code")
            if auth_err:
                error_code, description = auth_err
                ctx["error"] = description
                return render(request, "authorize.html", ctx)

            check = auth_service.verify_publive_credentials(publisher_id, api_key, api_secret)
            if not check.ok:
                if check.failure_reason == "missing_params":
                    logger.warning("OAuth authorize: missing params client=%s", client_id)
                    ctx["error"] = "All fields are required."
                elif check.failure_reason == "cds_unreachable":
                    logger.error(
                        "OAuth authorize: CDS unreachable publisher=%s client=%s",
                        publisher_id, client_id, exc_info=check.exc,
                    )
                    ctx["error"] = f"Could not reach Publive API: {check.detail}"
                else:  # cds_auth_failed
                    logger.warning(
                        "OAuth authorize: invalid CDS credentials publisher=%s client=%s status=%d",
                        publisher_id, client_id, check.status_code,
                    )
                    ctx["error"] = f"Invalid credentials (HTTP {check.status_code}). Check your Publisher ID, API Key, and API Secret."
                return render(request, "authorize.html", ctx)

            code: str = secrets.token_urlsafe(32)
            OAuthCode.objects.create_code(
                code=code,
                client_id=client_id,
                redirect_uri=redirect_uri,
                code_challenge=code_challenge,
                credentials={"publisherId": publisher_id, "apiKey": api_key, "apiSecret": api_secret},
                expires_at=timezone.now() + timedelta(minutes=10),
            )

            logger.info("OAuth authorize: success publisher=%s client=%s", publisher_id, client_id)
            return redirect(f"{redirect_uri}?{urlencode({'code': code, 'state': state})}")
        except Exception:
            logger.error("OAuth authorize: unhandled error client=%s", client_id, exc_info=True)
            raise
