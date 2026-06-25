"""Base class shared by the CDS and CMS HTTP service clients."""
import base64

import requests

# Shared tail of every "credentials rejected (HTTP 401)" message. Each site
# (the CDS/CMS clients and the CDS tool-dispatch error handler) prepends its own
# context sentence, then appends this identical re-authentication hint.
REAUTH_HINT = "Please re-authenticate: visit /connect or re-run the OAuth flow."


class BaseHttpClient:
    """Common helpers shared by the CDS and CMS HTTP service clients."""

    # --- Error-taxonomy knobs, overridden per subclass ----------------------
    SERVICE_NAME          = ""              # "CDS" / "CMS" — used in error messages
    INCLUDE_HTTP_STATUS   = False           # CDS adds http_status to every error dict
    CATEGORY_CLIENT_ERROR = "client_error"  # 4xx category name (CMS overrides: bad_request)
    CATEGORY_NOT_FOUND    = None            # CMS classifies 404 as not_found; CDS doesn't

    @staticmethod
    def slugify_url_path(path: str) -> str:
        """Convert a URL path to a flat slug for NR transaction naming."""
        slug = path.strip("/").replace("/", "_")
        return slug or "root"

    @staticmethod
    def build_base_url(template: str, credentials: dict) -> str:
        """Resolve a publisher-scoped base URL from credentials."""
        publisher_id = credentials.get("publisherId", "")
        if not publisher_id:
            return "No publisher ID in credentials — please re-authenticate"
        return template.format(publisher_id=publisher_id)

    @staticmethod
    def build_basic_auth_headers(credentials: dict) -> dict:
        """Return Authorization + Content-Type headers for Basic Auth."""
        api_key    = credentials.get("apiKey", "")
        api_secret = credentials.get("apiSecret", "")
        token = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode()
        return {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
        }

    # --- Shared error taxonomy ---------------------------------------------
    @classmethod
    def classify_error(cls, exc, http_status) -> str:
        """Map a failure to a standard error-category string (for NR instrumentation)."""
        if isinstance(exc, requests.exceptions.Timeout) or http_status == 408:
            return "timeout"
        if http_status == 401:
            return "auth_error"
        if http_status == 404 and cls.CATEGORY_NOT_FOUND:
            return cls.CATEGORY_NOT_FOUND
        if http_status and 400 <= http_status < 500:
            return cls.CATEGORY_CLIENT_ERROR
        if http_status and 500 <= http_status < 600:
            return "upstream_error"
        return "system_error"

    @classmethod
    def _error_dict(cls, error_type: str, message: str, retryable: bool, http_status) -> dict:
        """Build an error dict, adding http_status only when the subclass opts in."""
        result = {"error_type": error_type, "message": message, "retryable": retryable}
        if cls.INCLUDE_HTTP_STATUS:
            result["http_status"] = http_status
        return result

    @classmethod
    def _normalize_client_error(cls, exc, http_status, url: str) -> dict:
        """Default 4xx normalisation: plain message. CMS overrides to parse the body."""
        return cls._error_dict(cls.CATEGORY_CLIENT_ERROR, str(exc), False, http_status)

    @classmethod
    def normalize_error(cls, exc, url: str) -> dict:
        """Convert an HTTP failure into a structured error dict shared by both clients
        (timeout / 401 / 404 / 4xx / 5xx / fallback)."""
        http_status = getattr(getattr(exc, "response", None), "status_code", None)

        if isinstance(exc, requests.exceptions.Timeout) or http_status == 408:
            return cls._error_dict("timeout", f"{cls.SERVICE_NAME} request timed out.", True, http_status)
        if http_status == 401:
            return cls._error_dict(
                "auth_error",
                f"{cls.SERVICE_NAME} credentials rejected (HTTP 401). {REAUTH_HINT}",
                False, http_status,
            )
        if http_status == 404:
            return cls._error_dict("not_found", f"Resource not found ({url}).", False, http_status)
        if http_status and 400 <= http_status < 500:
            return cls._normalize_client_error(exc, http_status, url)
        if http_status and 500 <= http_status < 600:
            return cls._error_dict(
                "upstream_error",
                f"{cls.SERVICE_NAME} server error (HTTP {http_status}). Try again shortly.",
                True, http_status,
            )
        return cls._error_dict("system_error", str(exc), False, http_status)
