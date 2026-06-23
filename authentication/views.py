# Responsibility: HTTP view handlers for OAuth 2.0 PKCE flow and session-based auth.
import base64
from datetime import timedelta
import hashlib
import json
import logging
import secrets
import time
from typing import Optional
from urllib.parse import urlencode

from django.conf import settings
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from mcp.protocol.auth import build_unauthorized_response, resolve_credentials

from authentication.models import OAuthClient, OAuthCode, OAuthToken
from authentication.services import auth_service

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


# ── OAuth discovery ───────────────────────────────────────────────────────────

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


# ── Dynamic client registration ───────────────────────────────────────────────

@method_decorator(csrf_exempt, name="dispatch")
class OAuthRegisterView(View):
    """Register a new OAuth 2.0 client dynamically (one redirect_uri per client)."""

    def post(self, request: HttpRequest) -> JsonResponse:
        origin_err: Optional[JsonResponse] = auth_service.check_origin(request)
        if origin_err:
            return origin_err

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            body = {}

        # Accept either redirect_uris (list, legacy) or redirect_uri (string).
        raw_uris = body.get("redirect_uris", [])
        if isinstance(raw_uris, list) and raw_uris:
            redirect_uri: str = raw_uris[0]
        else:
            redirect_uri = str(body.get("redirect_uri", "")).strip()

        if redirect_uri and not auth_service.is_registrable_redirect_uri(redirect_uri):
            logger.warning("OAuth register: insecure redirect_uri=%s", redirect_uri)
            return JsonResponse(
                {
                    "error": "invalid_redirect_uri",
                    "error_description": "redirect_uri must use https:// or be a loopback address (http://localhost or http://127.0.0.1)",
                },
                status=400,
            )

        # os.urandom under the hood
        client_id: str = secrets.token_urlsafe(24)

        try:
            OAuthClient.objects.create_client(
                client_id=client_id,
                redirect_uri=redirect_uri,
            )
            logger.info("OAuth client registered: client_id=%s redirect_uri=%s", client_id, redirect_uri)
            return JsonResponse({
                "client_id": client_id,
                "client_id_issued_at": int(timezone.now().timestamp()),
                "redirect_uris": [redirect_uri] if redirect_uri else [],
            }, status=201)
        except Exception:
            logger.error("OAuth client registration failed", exc_info=True)
            raise


# ── Authorization endpoint ────────────────────────────────────────────────────

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


# ── Token endpoint ────────────────────────────────────────────────────────────

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


# ── Session-based auth (browser users) ───────────────────────────────────────

class ConnectView(View):
    """Render the browser-based session login page."""

    def get(self, request: HttpRequest) -> HttpResponse:
        return render(request, "connect.html")


class AuthSuccessView(View):
    """Render the post-login success page; redirect to /connect if session is missing."""

    def get(self, request: HttpRequest) -> HttpResponse:
        if not auth_service.get_session_credentials(request.session):
            return redirect("/connect")
        return render(request, "success.html")


@method_decorator(csrf_exempt, name="dispatch")
class AuthLoginView(View):
    """Validate Publive credentials via CDS, create a session, and set the user-chosen TTL."""

    def post(self, request: HttpRequest) -> JsonResponse:
        try:
            try:
                body = json.loads(request.body)
            except json.JSONDecodeError:
                return _auth_failure(
                    error="Invalid request body.", status=400,
                    log="auth_login: invalid JSON body",
                )

            publisher_id: str = str(body.get("publisherId", "")).strip()
            api_key: str      = str(body.get("apiKey", "")).strip()
            api_secret: str   = str(body.get("apiSecret", "")).strip()

            check = auth_service.verify_publive_credentials(publisher_id, api_key, api_secret)
            if check.failure_reason == "missing_params":
                return _auth_failure(
                    error="All fields are required.", status=400,
                    log="auth_login: missing params publisher=%s", log_args=(publisher_id,),
                )

            if check.failure_reason == "cds_unreachable":
                return _auth_failure(
                    error=f"Could not reach Publive API: {check.detail}", status=500,
                    log="auth_login: CDS unreachable publisher=%s", log_args=(publisher_id,),
                    log_level="error", exc_info=check.exc,
                )

            status_code = check.status_code
            if check.ok:
                now_ts: int = int(timezone.now().timestamp())   # Unix epoch — avoids fromisoformat py39 bug
                now_iso: str = timezone.now().isoformat()
                auth_service.set_session_credentials(request.session, {
                    "publisherId": publisher_id,
                    "apiKey": api_key,
                    "apiSecret": api_secret,
                })
                request.session["authenticatedAt"] = now_iso
                request.session["session_created_at"] = now_ts   # authoritative clock for TTL check (int epoch)
                request.session["session_ttl_seconds"] = -1      # never expires — only /auth/logout ends the session

                # Far-future absolute expiry so Django keeps the session alive until
                # the user explicitly disconnects via /auth/logout.
                request.session.set_expiry(10 * 365 * 24 * 3600)

                logger.info("auth_login: success publisher=%s", publisher_id)
                return JsonResponse({"success": True, "redirectTo": "/auth/success"})

            if status_code in (401, 403):
                err_msg, http_status = "Invalid credentials.", 401
            else:
                err_msg, http_status = f"HTTP {status_code}", 500
            return _auth_failure(
                error=err_msg, status=http_status,
                log="auth_login: invalid credentials publisher=%s status=%d",
                log_args=(publisher_id, status_code),
            )
        except Exception:
            logger.error("auth_login: unhandled error", exc_info=True)
            raise


class AuthStatusView(View):
    """Return the current session state including publisher ID, login time, and TTL."""

    def get(self, request: HttpRequest) -> JsonResponse:
        try:
            credentials = auth_service.get_session_credentials(request.session)
            if credentials:
                # Enforce server-side absolute TTL — catches sessions that Django's
                # cookie TTL would miss (e.g. SESSION_SAVE_EVERY_REQUEST disabled).
                if auth_service.check_session_ttl(request.session):
                    request.session.flush()
                    return JsonResponse({"authenticated": False, "error": "SESSION_EXPIRED"})

                ttl_seconds: int = request.session.get("session_ttl_seconds", -1)
                if ttl_seconds == -1:
                    expires_in: Optional[int] = None          # never
                elif ttl_seconds == 0:
                    expires_in = None                          # browser-controlled
                else:
                    created_at_ts = request.session.get("session_created_at", 0)
                    try:
                        deadline_ts = int(created_at_ts) + int(ttl_seconds)
                        expires_in = max(0, int(deadline_ts - time.time()))
                    except (ValueError, TypeError):
                        expires_in = request.session.get_expiry_age()

                return JsonResponse({
                    "authenticated": True,
                    "publisherId": credentials.get("publisherId"),
                    "authenticatedAt": request.session.get("authenticatedAt"),
                    "session_expires_in_seconds": expires_in,
                })

            return JsonResponse({"authenticated": False})
        except Exception:
            logger.error("auth_status: unhandled error", exc_info=True)
            raise


@method_decorator(csrf_exempt, name="dispatch")
class AuthLogoutView(View):
    """Flush the current session and log the publisher out."""

    def post(self, request: HttpRequest) -> JsonResponse:
        creds = auth_service.get_session_credentials(request.session)
        publisher_id: str = (creds or {}).get("publisherId", "unknown")
        request.session.flush()
        logger.info("auth_logout: publisher=%s", publisher_id)
        return JsonResponse({"success": True})


# ── Token revocation (RFC 7009) ───────────────────────────────────────────────

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


# ── UserInfo (OIDC-style identity claims) ─────────────────────────────────────

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
