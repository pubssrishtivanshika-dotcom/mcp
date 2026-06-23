import base64
import json
import logging
import time
from typing import Any, NamedTuple, Optional
from urllib.parse import parse_qs, urlsplit

from cryptography.fernet import InvalidToken
from django.conf import settings
from django.http import HttpRequest, JsonResponse
import requests

from authentication.crypto import decrypt_credentials, encrypt_credentials

logger = logging.getLogger(__name__)


class CredentialCheck(NamedTuple):
    """Outcome of verifying Publive credentials against the CDS API."""

    ok: bool
    # One of: "missing_params" | "cds_unreachable" | "cds_auth_failed" (None when ok).
    failure_reason: Optional[str] = None
    status_code: Optional[int] = None
    detail: Optional[str] = None
    exc: Optional[BaseException] = None


class AuthService:
    """Business-logic helpers for the OAuth / session auth flows."""

    _LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

    def get_session_credentials(self, session) -> Optional[dict]:
        """Return the credentials dict stored in the session, or None if absent.

        Credentials are encrypted at rest in the DB-backed session (see
        set_session_credentials); decryption is tolerant of legacy plaintext sessions.
        """
        raw = session.get("credentials")
        if raw is None:
            return None
        try:
            creds = decrypt_credentials(raw)
        except InvalidToken:
            logger.warning("get_session_credentials: undecryptable session credentials")
            return None
        return creds if isinstance(creds, dict) else None

    def set_session_credentials(self, session, credentials: dict) -> None:
        """Store credentials in the session, encrypted at rest."""
        session["credentials"] = encrypt_credentials(credentials)

    def check_session_ttl(self, session) -> bool:
        """Return True if the session has exceeded its original TTL.


        Django's rolling SESSION_SAVE_EVERY_REQUEST is intentionally disabled so
        these stored values are the authoritative expiry source.
        """
        ttl_seconds = session.get("session_ttl_seconds", -1)
        if ttl_seconds <= 0:
            return False
        created_at_ts = session.get("session_created_at")
        if not created_at_ts:
            return False
        try:
            deadline_ts = int(created_at_ts) + int(ttl_seconds)
            return time.time() > deadline_ts
        except (ValueError, TypeError):
            return False

    def get_allowed_origins(self) -> set[str]:
        """Return the set of permitted browser Origins (normalized, no trailing slash).

        The authentication.AllowedOrigin table is the single source of truth, read directly
        from the DB on every call. The table is seeded on first migration (authentication
        0003) and managed at runtime in the DB. On a DB error the result is left empty
        so check_origin fails closed (browser Origins blocked); Origin-less desktop
        clients and same-origin BASE_URL requests are unaffected.
        """
        try:
            from authentication.models import AllowedOrigin   # legitimate lazy import to avoid a circular models ↔ services dependency, not a redundancy

            return {
                o.rstrip("/")
                for o in AllowedOrigin.objects.filter(is_active=True).values_list(
                    "origin", flat=True
                )
            }
        except Exception:  # table missing / DB error — fail closed
            logger.warning("OAuth: could not load AllowedOrigin from DB; blocking browser origins this request")
            return set()

    def check_origin(self, request: HttpRequest) -> Optional[JsonResponse]:
        """Return None if the Origin header is acceptable; return a 403 JsonResponse otherwise.

        Desktop MCP clients (Claude Desktop, Cursor) do not send an Origin header because
        they are not browsers — those are unconditionally allowed. When an Origin IS present
        (web-based Claude clients), it must appear in the AllowedOrigin table (see
        get_allowed_origins).
        """
        origin: str = request.META.get("HTTP_ORIGIN", "").rstrip("/")
        if not origin:
            return None

        allowed = set(self.get_allowed_origins())
        allowed.add(settings.BASE_URL.rstrip("/"))  # always allow same-origin

        if origin in allowed:
            return None

        logger.warning("OAuth: blocked request from disallowed origin=%r", origin)
        return JsonResponse(
            {"error": "invalid_origin", "error_description": "Origin not allowed"},
            status=403,
        )

    def is_loopback_redirect_uri(self, uri: str) -> bool:
        """Return True for http://localhost:<port>/... or http://127.0.0.1:<port>/... URIs.

        Native/desktop OAuth clients (RFC 8252 §7.3) bind an ephemeral local port at
        launch and can't be allowlisted by exact string match — the authorization
        server must accept any port for these.
        """
        try:
            parts = urlsplit(uri)
        except ValueError:
            return False
        return parts.scheme == "http" and parts.hostname in self._LOOPBACK_HOSTS

    def is_registrable_redirect_uri(self, uri: str) -> bool:
        """Return True for redirect URIs acceptable at dynamic client registration.

        Per RFC 7591 / OAuth 2.1, registration is open to any client — the server
        doesn't pre-approve specific apps by URL. The only requirement is transport
        security: either HTTPS (web/mobile callbacks) or a loopback address (native
        apps per RFC 8252 §7.3, which can't use HTTPS for an ephemeral local port).
        Plain http:// to a non-loopback host is rejected as it would leak the
        authorization code over an insecure channel.
        """
        try:
            parts = urlsplit(uri)
        except ValueError:
            return False
        if parts.scheme == "https" and parts.hostname:
            return True
        return self.is_loopback_redirect_uri(uri)

    def redirect_uris_match(self, requested: str, registered: str) -> bool:
        """Return True when redirect URIs match exactly, or both are loopback URIs
        that differ only by port.

        RFC 8252 §7.3: the authorization server MUST allow any port to be specified
        at request time for loopback redirect URIs, since native apps obtain an
        ephemeral port from the OS when they start listening.
        """
        if requested == registered:
            return True
        if not (self.is_loopback_redirect_uri(requested) and self.is_loopback_redirect_uri(registered)):
            return False
        req, reg = urlsplit(requested), urlsplit(registered)
        return (req.scheme, req.hostname, req.path) == (reg.scheme, reg.hostname, reg.path)

    def parse_oauth_token_body(self, request: HttpRequest) -> tuple[Optional[dict[str, Any]], Optional[JsonResponse]]:
        """Parse /oauth/token request body from JSON or application/x-www-form-urlencoded."""
        content_type = (request.content_type or "").split(";", 1)[0].strip().lower()

        if content_type == "application/json":
            try:
                body = json.loads(request.body)
            except json.JSONDecodeError:
                return None, JsonResponse({"error": "invalid_request"}, status=400)
            if not isinstance(body, dict):
                return None, JsonResponse({"error": "invalid_request"}, status=400)
            return body, None

        if content_type == "application/x-www-form-urlencoded":
            if request.POST:
                return request.POST.dict(), None
            try:
                parsed = parse_qs(request.body.decode("utf-8"), keep_blank_values=True)
            except UnicodeDecodeError:
                return None, JsonResponse({"error": "invalid_request"}, status=400)
            return {key: values[0] if values else "" for key, values in parsed.items()}, None

        return None, JsonResponse(
            {
                "error": "invalid_request",
                "error_description": "Content-Type must be application/x-www-form-urlencoded or application/json",
            },
            status=400,
        )

    def validate_cds_credentials(
        self,
        publisher_id: str,
        api_key: str,
        api_secret: str,
    ) -> tuple[bool, int]:
        """Call the Publive CDS API to verify credentials; return (is_valid, http_status).
        Raises requests.RequestException if the CDS is unreachable — callers must handle it.
        """
        token: str = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode()
        t0: float = time.perf_counter()
        # Validate against the publisher root — the smallest authenticated GET that
        # exists for every publisher (returns 401 without valid Basic auth, 200 with).
        # We previously probed `/posts/?limit=1`, but that endpoint now requires a
        # `field__eq` filter expression on some publishers and 400s on a bare call,
        # which is indistinguishable from bad credentials. The root has no such
        # requirement. Use the same env-configurable base URL as the CDS client.
        base = settings.CDS_BASE_URL.format(publisher_id=publisher_id)
        resp = requests.get(
            f"{base}/",
            headers={"Authorization": f"Basic {token}"},
            timeout=10,
        )
        latency_ms: float = round((time.perf_counter() - t0) * 1000, 2)
        logger.info(
            "CDS validation: publisher=%s status=%d latency_ms=%.2f",
            publisher_id, resp.status_code, latency_ms,
        )
        # Only a 2xx means the credentials are genuinely valid.
        return 200 <= resp.status_code < 300, resp.status_code

    def verify_publive_credentials(
        self,
        publisher_id: str,
        api_key: str,
        api_secret: str,
    ) -> CredentialCheck:
        """Run the shared credential-validation pipeline used by both the OAuth
        authorize and session-login flows: require all three fields, then verify
        them against the CDS API.

        Pure decision logic that never raises — CDS unreachability is reported as a
        cds_unreachable outcome rather than propagating requests.RequestException —
        so each caller can map the result onto its own telemetry and response shape.
        """
        if not all([publisher_id, api_key, api_secret]):
            return CredentialCheck(False, "missing_params")
        try:
            ok, status_code = self.validate_cds_credentials(publisher_id, api_key, api_secret)
        except requests.RequestException as exc:
            return CredentialCheck(False, "cds_unreachable", detail=str(exc), exc=exc)
        if not ok:
            return CredentialCheck(False, "cds_auth_failed", status_code=status_code)
        return CredentialCheck(True, status_code=status_code)


# Module-level singleton — the shared auth service object.
auth_service = AuthService()

