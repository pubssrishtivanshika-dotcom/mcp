"""Streamable HTTP transport for MCP (stateless POST /mcp)."""
import json
import logging

from django.http import HttpResponse, JsonResponse

from mcp.protocol.dispatch import dispatch_jsonrpc, jsonrpc_error
from mcp.protocol.session import (
    DEFAULT_NEGOTIATED_PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    derive_session_id,
)

logger = logging.getLogger(__name__)


def _is_initialize_request(body) -> bool:
    """True if this HTTP request carries an initialize call (which establishes the
    protocol version and therefore does not itself send MCP-Protocol-Version)."""
    if isinstance(body, dict):
        return body.get("method") == "initialize"
    if isinstance(body, list):
        return any(isinstance(m, dict) and m.get("method") == "initialize" for m in body)
    return False


def handle_http_request(request, credentials: dict, token_expires_at) -> HttpResponse:
    """Process a single stateless POST /mcp request (Streamable HTTP transport)."""
    request_size = len(request.body)
    session_id   = derive_session_id(request)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        logger.warning("handle_http_request: invalid JSON: size=%d", request_size)
        return JsonResponse(jsonrpc_error(None, -32700, "Parse error"))

    # MCP-Protocol-Version header: required on every request after initialize.
    # Absent → assume the pre-header revision (spec back-compat); present but
    # unsupported → 400. The initialize request itself never carries it.
    if not _is_initialize_request(body):
        header_version = request.META.get("HTTP_MCP_PROTOCOL_VERSION")
        if header_version is None:
            header_version = DEFAULT_NEGOTIATED_PROTOCOL_VERSION
        elif header_version not in SUPPORTED_PROTOCOL_VERSIONS:
            logger.warning(
                "handle_http_request: unsupported MCP-Protocol-Version=%r session=%s",
                header_version, session_id,
            )
            return JsonResponse(
                {
                    "error": "unsupported_protocol_version",
                    "error_description": f"Unsupported MCP-Protocol-Version: {header_version}",
                },
                status=400,
            )

    try:
        if isinstance(body, list):
            logger.debug("MCP batch request: count=%d session=%s", len(body), session_id)
            responses = [
                r for r in (
                    dispatch_jsonrpc(msg, credentials, request, session_id, token_expires_at)
                    for msg in body
                )
                if r is not None
            ]
            return JsonResponse(responses, safe=False) if responses else HttpResponse(status=202)

        response = dispatch_jsonrpc(body, credentials, request, session_id, token_expires_at)
        if response is None:
            return HttpResponse(status=202)
        return JsonResponse(response)

    except Exception:
        logger.error("handle_http_request transport error: session=%s", session_id, exc_info=True)
        raise
