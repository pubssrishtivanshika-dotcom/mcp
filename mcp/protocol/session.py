"""Session ID derivation and protocol-version constants."""
import hashlib
import uuid

SESSION_PROTOCOL_KEY = "mcp_protocol_version"
_SESSION_PROTOCOL_KEY = SESSION_PROTOCOL_KEY  # backward-compat alias

# MCP protocol revisions this server speaks. LATEST is what we advertise during
# initialize when the client requests something we don't recognise; the full set
# is what we accept (via the MCP-Protocol-Version header) on subsequent requests.
LATEST_PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = frozenset({
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
})

# Per the spec, a request that omits MCP-Protocol-Version is assumed to be this
# revision for backwards compatibility.
DEFAULT_NEGOTIATED_PROTOCOL_VERSION = "2025-03-26"


def derive_session_id(request) -> str:
    """Return a stable session identifier for this request.

    Priority:
    1. Django session key  (browser / session-cookie clients)
    2. SHA-256 prefix of Bearer token  (OAuth clients — same token → same ID across requests)
    3. Transient UUID  (unauthenticated or sessionless probes)
    """
    key = getattr(request.session, "session_key", None)
    if key:
        return key

    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer "):]
        return "oauth-" + hashlib.sha256(token.encode()).hexdigest()[:16]

    return "anon-" + uuid.uuid4().hex[:8]
