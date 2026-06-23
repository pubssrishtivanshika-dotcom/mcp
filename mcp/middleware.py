"""Middleware stack for the Publive MCP server.

RequestIDMiddleware   — attach a correlation ID to every request/response
SecurityHeadersMiddleware — CSP + X-Frame-Options + nosniff on every HTML response
"""
import logging
import uuid

logger = logging.getLogger(__name__)


class RequestIDMiddleware:
    """Attach a request ID to every request/response for log correlation.

    Reads X-Request-ID from the incoming request if present; otherwise generates
    a UUID4. The ID is stored on request.request_id and echoed back in the
    X-Request-ID response header so callers can correlate logs with their requests.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.META.get("HTTP_X_REQUEST_ID", "") or str(uuid.uuid4())
        request.request_id = request_id
        response = self.get_response(request)
        response["X-Request-ID"] = request_id
        return response


class SecurityHeadersMiddleware:
    """Add security headers to every HTML response served by the auth pages.

    Applied only to text/html responses so JSON API endpoints are unaffected.
    Prevents clickjacking (X-Frame-Options), MIME sniffing (nosniff), and
    cross-site scripting via a restrictive Content-Security-Policy.
    """

    _CSP = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if "text/html" in response.get("Content-Type", ""):
            response.setdefault("Content-Security-Policy", self._CSP)
            response.setdefault("X-Frame-Options", "DENY")
            response.setdefault("X-Content-Type-Options", "nosniff")
            response.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
            response.setdefault("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
        return response
