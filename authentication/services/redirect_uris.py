# Responsibility: Redirect-URI validation and matching for the OAuth flows (RFC 7591 / 8252).
from urllib.parse import urlsplit


class RedirectUriMixin:
    """Redirect-URI helpers for the auth service."""

    _LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

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
