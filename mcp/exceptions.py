"""Typed exceptions raised across the MCP app.

Replaces bare ``raise Exception(...)`` calls and the
``exc = Exception(...); exc.response = resp`` hack that smuggled an HTTP
response into the client error normalisers. Carrying the response on a real
exception type lets ``normalize_error`` / ``classify_error`` read
``status_code`` without fabricating an exception, and lets callers catch
precisely (``except MissingPublisherError`` etc.) instead of ``except Exception``.
"""


class PubliveError(Exception):
    """Base class for all application-specific errors."""


class MissingPublisherError(PubliveError):
    """Credentials lacked the publisher ID needed to build a base URL."""


class UnknownToolError(PubliveError):
    """A tool name was dispatched that has no registered handler."""


class HttpClientError(PubliveError):
    """An upstream API returned a non-2xx response.

    Carries the originating ``requests.Response`` so the error normalisers can
    read ``status_code`` and the response body without a fabricated exception.
    """

    def __init__(self, message: str, response=None):
        super().__init__(message)
        self.response = response

    @property
    def status_code(self):
        return getattr(self.response, "status_code", None)


class CdsClientError(HttpClientError):
    """A CDS API request failed with a non-2xx response."""


class CmsClientError(HttpClientError):
    """A CMS API request failed with a non-2xx response."""
