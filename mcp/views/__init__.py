"""MCP view router — authenticates every request then delegates to the right transport view."""
import logging

from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from authentication.services import auth_service
from mcp.protocol.auth import build_unauthorized_response, identify_mcp_client, resolve_credentials
from mcp.views.http import http_mcp

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class MCPEndpointView(View):
    """Single entry point for POST /mcp (Streamable HTTP transport).
    Validates Origin, resolves credentials once, then hands off to the transport view."""

    def post(self, request):
        auth = self._authenticate(request)
        if isinstance(auth, HttpResponse):
            return auth
        credentials, token_expires_at = auth
        return http_mcp(request, credentials, token_expires_at)

    def _authenticate(self, request):
        """Validate Origin and resolve credentials. Returns an HttpResponse on
        failure, or (credentials, token_expires_at) on success."""
        origin_error = auth_service.check_origin(request)
        if origin_error is not None:
            return origin_error

        has_bearer = request.META.get("HTTP_AUTHORIZATION", "").startswith("Bearer ")
        identify_mcp_client(request)
        logger.info(
            "MCP request: method=%s has_bearer=%s ua=%s",
            request.method,
            has_bearer,
            request.META.get("HTTP_USER_AGENT", "unknown")[:80],
        )

        credentials, token_expires_at, error_code = resolve_credentials(request)
        if error_code or not credentials:
            logger.warning(
                "MCP authentication failed: method=%s has_bearer=%s error_code=%s",
                request.method, has_bearer, error_code,
            )
            return build_unauthorized_response(request, error_code=error_code)

        logger.info("MCP authenticated: method=%s", request.method)
        return credentials, token_expires_at


# Back-compat: `from mcp.views import mcp_endpoint` resolves to the .as_view()
# callable. Django's View returns 405 for unimplemented methods (e.g. GET /mcp).
mcp_endpoint = MCPEndpointView.as_view()
