"""HTTP client for the Publive CMS (Content Management System) API.

Covers GET / POST / PATCH / DELETE.  No automatic retry (write operations are not idempotent).
All error paths return a normalised error dict instead of raising so callers can inspect the
error_type and decide whether to surface a message or propagate.
"""
import json
import logging

from django.conf import settings
import requests

from mcp.exceptions import CmsClientError

from mcp.clients.shared import BaseHttpClient

logger = logging.getLogger(__name__)


class CmsClient(BaseHttpClient):
    """HTTP client for the Publive CMS API (GET / POST / PATCH / DELETE)."""

    # Env-configurable (CMS_BASE_URL); defaults to the beta host in settings.
    BASE            = settings.CMS_BASE_URL
    REQUEST_TIMEOUT = 10  # seconds

    # Error-taxonomy knobs consumed by BaseHttpClient.classify_error / normalize_error.
    # CMS reports 4xx as bad_request and special-cases 404 as not_found; it does not
    # add http_status to its error dicts (INCLUDE_HTTP_STATUS defaults to False).
    SERVICE_NAME          = "CMS"
    CATEGORY_CLIENT_ERROR = "bad_request"
    CATEGORY_NOT_FOUND    = "not_found"

    @classmethod
    def _normalize_client_error(cls, exc, http_status, url: str) -> dict:
        """CMS-specific 4xx normalisation: parse the response body for a detail/
        message/field-error string and attach a truncated raw_api_response copy."""
        msg      = f"HTTP {http_status}"
        raw_body = ""
        try:
            raw_body = exc.response.text[:1000]
            data     = exc.response.json()
            msg      = (
                data.get("detail")
                or data.get("message")
                or (data.get("error") or {}).get("description")
                or msg
            )
            if msg == f"HTTP {http_status}" and isinstance(data, dict):
                field_errors = []
                for key, val in data.items():
                    if isinstance(val, list):
                        field_errors.append(f"{key}: {', '.join(str(v) for v in val)}")
                    elif isinstance(val, str):
                        field_errors.append(f"{key}: {val}")
                if field_errors:
                    msg = "Validation error — " + "; ".join(field_errors)
        except (ValueError, json.JSONDecodeError, AttributeError, KeyError):
            pass
        logger.warning("cms_client 4xx: url=%s status=%d raw_body=%s", url, http_status, raw_body)
        return {"error_type": cls.CATEGORY_CLIENT_ERROR, "message": msg, "raw_api_response": raw_body, "retryable": False}

    def _request(self, method: str, credentials: dict, path: str, *, params=None, body=None):
        """Single code path for every CMS verb.

        ``method`` is an upper-case HTTP verb. GET passes ``params``; POST/PATCH pass a
        JSON ``body``; DELETE passes neither and tolerates an empty (204) response. The
        HTTP function is resolved off ``requests`` by name at call time so test patches of
        ``requests.get`` / ``requests.post`` etc. are honoured.
        """
        url          = self.build_base_url(self.BASE, credentials) + path
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        http_fn = getattr(requests, method.lower())
        try:
            resp = http_fn(url, headers=self.build_basic_auth_headers(credentials), params=clean_params, json=body, timeout=self.REQUEST_TIMEOUT)
            if not resp.ok:
                exc = CmsClientError(f"HTTP {resp.status_code}", response=resp)
                return self.normalize_error(exc, url)
            if method == "DELETE" and (resp.status_code == 204 or not resp.content):
                return {"status": "deleted", "http_status": resp.status_code}
            return resp.json()
        except requests.exceptions.Timeout:
            return {"error_type": "timeout", "message": "CMS request timed out.", "retryable": True}
        except requests.exceptions.ConnectionError:
            return {"error_type": "system_error", "message": "Could not connect to CMS API.", "retryable": True}
        except Exception as exc:
            logger.error("cms_%s unexpected error: path=%s error=%s", method.lower(), path, exc, exc_info=True)
            raise

    def get(self, credentials: dict, path: str, params=None):
        return self._request("GET", credentials, path, params=params)

    def post(self, credentials: dict, path: str, body: dict):
        return self._request("POST", credentials, path, body=body)

    def patch(self, credentials: dict, path: str, body: dict):
        return self._request("PATCH", credentials, path, body=body)

    def delete(self, credentials: dict, path: str):
        return self._request("DELETE", credentials, path)


# Module-level singleton — the shared CMS service object.
cms_client = CmsClient()
