# Responsibility: Session-based browser auth (connect, login, success, status, logout).
import json
import logging
import time
from typing import Optional

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from authentication.services import auth_service
from authentication.views.helpers import _auth_failure

logger = logging.getLogger(__name__)


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
