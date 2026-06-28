"""JSON-RPC dispatcher — routes initialize / tools/list / tools/call to the right handler."""
import json
import logging
import time

import newrelic.agent
from django.conf import settings

from mcp.cds import TOOLS, dispatch_cds_tool
from mcp.cms import CMS_TOOL_NAMES, CMS_TOOLS, dispatch_cms_tool
from mcp.prompt_capture import strip_prompt_from_args

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

from mcp.protocol.session import (
    LATEST_PROTOCOL_VERSION,
    SESSION_PROTOCOL_KEY,
    SUPPORTED_PROTOCOL_VERSIONS,
)

logger = logging.getLogger(__name__)


def negotiate_protocol_version(requested) -> str:
    """Return the protocol version to respond with during initialize.

    Echo the client's requested version when we support it; otherwise advertise
    our latest so the client can decide whether to proceed (MCP spec behaviour).
    """
    if isinstance(requested, str) and requested in SUPPORTED_PROTOCOL_VERSIONS:
        return requested
    return LATEST_PROTOCOL_VERSION

# ── Input schema validation ───────────────────────────────────────────────────

# Pre-built name → inputSchema lookup for all 71 tools
_SCHEMA_REGISTRY: dict = {
    tool["name"]: tool.get("inputSchema", {})
    for tool in (TOOLS + CMS_TOOLS)
}

# Lazily-built, cached Draft 2020-12 validator per tool name. Building from
# _SCHEMA_REGISTRY on demand keeps tests free to register ad-hoc schemas.
_VALIDATOR_CACHE: dict = {}


def _validator_for(name: str):
    """Return a cached jsonschema validator for the tool, or None if unknown."""
    validator = _VALIDATOR_CACHE.get(name)
    if validator is not None:
        return validator
    schema = _SCHEMA_REGISTRY.get(name)
    if schema is None:
        return None
    validator = Draft202012Validator(schema)
    _VALIDATOR_CACHE[name] = validator
    return validator


def _validate_tool_args(name: str, args: dict) -> dict:
    """Validate args against the tool's inputSchema via jsonschema.

    Returns an ``invalid_params`` error dict on the first/most-relevant
    violation, or ``None`` when the args are valid (or the tool is unknown).
    jsonschema covers nested objects, enums, formats, numeric ranges and
    string constraints — everything declared in each tool's inputSchema.
    """
    validator = _validator_for(name)
    if validator is None:
        return None

    error = best_match(validator.iter_errors(args))
    if error is None:
        return None

    field   = ".".join(str(p) for p in error.absolute_path)
    message = f"Field '{field}': {error.message}" if field else error.message
    return {
        "error_type": "invalid_params",
        "message": message,
        "retryable": False,
    }

_UNIMPLEMENTED_METHODS: frozenset[str] = frozenset({
    "sampling/createMessage",
    "roots/list",
    "resources/list",
    "resources/read",
    "resources/subscribe",
    "resources/unsubscribe",
    "prompts/list",
    "prompts/get",
    "completion/complete",
    "logging/setLevel",
})


def jsonrpc_ok(id_, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def jsonrpc_error(id_, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def classify_tool_error(exc) -> str:
    """Map a tool exception to a standard error category string for logging."""
    http_status = getattr(getattr(exc, "response", None), "status_code", None)
    exc_lower   = str(exc).lower()
    if http_status == 408 or "timeout" in exc_lower or "timed out" in exc_lower:
        return "timeout"
    if http_status == 401:
        return "auth_error"
    if http_status and 400 <= http_status < 500:
        return "client_error"
    if http_status and 500 <= http_status < 600:
        return "upstream_error"
    return "system_error"


def dispatch_jsonrpc(body: dict, credentials: dict, request=None, session_id=None, token_expires_at=None):
    """Route a single JSON-RPC body to the correct handler and return the response dict."""
    method = body.get("method", "")
    id_    = body.get("id")

    if id_ is None:
        logger.debug("MCP notification: method=%s (no response)", method)
        return None

    # ── initialize ────────────────────────────────────────────────────────────
    if method == "initialize":
        requested_version = body.get("params", {}).get("protocolVersion")
        protocol_version  = negotiate_protocol_version(requested_version)
        if request is not None:
            request.session[SESSION_PROTOCOL_KEY] = protocol_version
        logger.info(
            "MCP initialize: session=%s protocol=%s requested=%s",
            session_id, protocol_version, requested_version,
        )
        result = {
            "protocolVersion": protocol_version,
            "capabilities":    {"tools": {}},
            "serverInfo":      {"name": "publive-cds", "version": settings.SERVER_VERSION},
        }
        if token_expires_at is not None:
            result["tokenExpiresAt"] = token_expires_at.isoformat()
        return jsonrpc_ok(id_, result)

    # ── tools/list ────────────────────────────────────────────────────────────
    if method == "tools/list":
        all_tools = TOOLS + CMS_TOOLS
        logger.debug("MCP tools/list: session=%s count=%d", session_id, len(all_tools))
        return jsonrpc_ok(id_, {"tools": all_tools})

    # ── tools/call ────────────────────────────────────────────────────────────
    if method == "tools/call":
        return _handle_tool_call(body, credentials, request, session_id, id_)

    # ── ping ──────────────────────────────────────────────────────────────────
    if method == "ping":
        logger.debug("MCP ping: session=%s", session_id)
        return jsonrpc_ok(id_, {})

    # ── known-but-unimplemented ───────────────────────────────────────────────
    if method in _UNIMPLEMENTED_METHODS:
        logger.debug("MCP method not implemented (expected): method=%s session=%s", method, session_id)
        return jsonrpc_error(id_, -32601, f"Method not found: {method}")

    # ── truly unknown ─────────────────────────────────────────────────────────
    logger.warning("MCP unknown method: method=%s session=%s id=%s", method, session_id, id_)
    return jsonrpc_error(id_, -32601, f"Method not found: {method}")


def _handle_tool_call(body: dict, credentials: dict, request, session_id, id_) -> dict:
    """Execute a single tools/call request and return the JSON-RPC response."""
    params = body.get("params", {})
    name   = params.get("name", "")
    args   = strip_prompt_from_args(params)

    # Tag the New Relic transaction with the tool name up front, so the attribute
    # is present even when the call fails validation or raises before completion.
    newrelic.agent.add_custom_attribute("mcp.tool", name)

    logger.info(
        "MCP tools/call: tool=%s session=%s args_count=%d",
        name, session_id, len(args) if args else 0,
    )

    # Validate arguments against the tool's inputSchema before dispatching
    validation_error = _validate_tool_args(name, args or {})
    if validation_error:
        logger.warning(
            "MCP tools/call validation error: tool=%s session=%s message=%s",
            name, session_id, validation_error.get("message"),
        )
        return jsonrpc_ok(id_, {
            "content": [{"type": "text", "text": json.dumps(validation_error)}],
            "isError": True,
        })

    t0 = time.perf_counter()
    try:
        result      = dispatch_cms_tool(credentials, name, args) if name in CMS_TOOL_NAMES else dispatch_cds_tool(credentials, name, args)
        duration_ms = round((time.perf_counter() - t0) * 1000, 2)

        degraded_reason = (result.get("error") or result.get("error_type")) if isinstance(result, dict) else None

        # Per-tool latency + outcome for New Relic FACET mcp.tool dashboards.
        newrelic.agent.add_custom_attribute("mcp.duration_ms", duration_ms)
        newrelic.agent.add_custom_attribute("mcp.status", "degraded" if degraded_reason else "success")

        if result in (None, "", [], {}, ()):
            output_text = json.dumps({
                "status": "no_data",
                "message": "The tool returned no data for this request.",
            })
        else:
            output_text = json.dumps(result, indent=2)
        result_size = len(output_text)

        if degraded_reason:
            logger.warning("MCP tools/call degraded: tool=%s reason=%s duration_ms=%.2f", name, degraded_reason, duration_ms)
        else:
            logger.info("MCP tools/call success: tool=%s duration_ms=%.2f response_size=%d", name, duration_ms, result_size)

        # Surface upstream errors/degraded results to the client model via the MCP
        # isError flag so it treats them as failures, not as data to reason over.
        response = {"content": [{"type": "text", "text": output_text}]}
        if degraded_reason:
            response["isError"] = True
        return jsonrpc_ok(id_, response)

    except Exception as exc:
        duration_ms    = round((time.perf_counter() - t0) * 1000, 2)
        error_category = classify_tool_error(exc)
        newrelic.agent.add_custom_attribute("mcp.duration_ms", duration_ms)
        newrelic.agent.add_custom_attribute("mcp.status", "error")
        newrelic.agent.add_custom_attribute("mcp.error_category", error_category)
        logger.error(
            "MCP tools/call error: tool=%s session=%s category=%s error=%s duration_ms=%.2f",
            name, session_id, error_category, exc, duration_ms, exc_info=True,
        )
        return jsonrpc_ok(id_, {"content": [{"type": "text", "text": f"Error: {exc}"}], "isError": True})
