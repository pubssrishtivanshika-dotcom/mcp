"""HTTP client for the Publive CDS (Content Delivery System) API.

Read-only. Retries once on transient failures (timeout, HTTP 408).
All error paths return a normalised error dict (mirroring the CMS client) instead
of raising, so callers can inspect ``error_type`` and decide whether to surface a
message or propagate.
"""
import json
import logging
import time

from django.conf import settings
import requests

from mcp.clients.shared import BaseHttpClient

logger = logging.getLogger(__name__)


class CdsClient(BaseHttpClient):
    """Read-only HTTP client for the Publive CDS API."""

    # Env-configurable (CDS_BASE_URL); defaults to the beta host in settings.
    BASE            = settings.CDS_BASE_URL
    REQUEST_TIMEOUT = 5   # seconds per attempt
    RETRY_BACKOFF   = 1   # seconds between attempts

    # Error-taxonomy knobs consumed by BaseHttpClient.classify_error / normalize_error.
    # CDS reports 4xx as client_error, does not special-case 404 in classify_error,
    # and includes http_status on every normalised error dict.
    SERVICE_NAME          = "CDS"
    INCLUDE_HTTP_STATUS   = True
    CATEGORY_CLIENT_ERROR = "client_error"

    @staticmethod
    def is_retryable_error(exc) -> bool:
        """True for transient failures worth retrying once."""
        if isinstance(exc, requests.exceptions.Timeout):
            return True
        status = getattr(getattr(exc, "response", None), "status_code", None)
        return status == 408

    @staticmethod
    def is_not_found(error: dict) -> bool:
        """True when a normalised CDS error dict represents a missing resource/endpoint."""
        if not isinstance(error, dict) or "error_type" not in error:
            return False
        if error.get("http_status") in (400, 404) or error.get("error_type") == "not_found":
            return True
        message = str(error.get("message", "")).lower()
        return "unknown endpoint" in message or "not found" in message or "no such" in message

    def get(self, credentials: dict, path: str, params=None):
        """GET a CDS endpoint; retry once on timeout or HTTP 408."""
        publisher_id = credentials.get("publisherId", "")
        if not publisher_id:
            return {
                "error_type": "auth_error",
                "message": "No publisher ID in credentials — please re-authenticate.",
                "retryable": False,
                "http_status": None,
            }

        headers = self.build_basic_auth_headers(credentials)
        url     = self.build_base_url(self.BASE, credentials) + path

        clean_params = {k: v for k, v in (params or {}).items() if v is not None and v != ""}

        t0          = time.perf_counter()
        last_exc    = None
        retry_count = 0

        for attempt in range(2):
            if attempt > 0:
                time.sleep(self.RETRY_BACKOFF)
                retry_count = attempt
                logger.warning("CDS retry attempt %d: path=%s publisher=%s", attempt, path, publisher_id)

            try:
                resp = requests.get(
                    url,
                    headers={"Authorization": headers["Authorization"]},
                    params=clean_params,
                    timeout=self.REQUEST_TIMEOUT,
                )
                latency_ms = round((time.perf_counter() - t0) * 1000, 2)

                if not resp.ok:
                    try:
                        data = resp.json()
                        msg  = data.get("detail") or data.get("message") or f"HTTP {resp.status_code}"
                    except (ValueError, json.JSONDecodeError):
                        msg = f"HTTP {resp.status_code}"
                    exc = "CdsClientError"
                    if resp.status_code == 408 and attempt == 0:
                        last_exc = exc
                        continue
                    return exc

                response_size = len(resp.content)
                logger.info(
                    "CDS request: path=%s publisher=%s status=%d latency_ms=%.2f size=%d retry=%d",
                    path, publisher_id, resp.status_code, latency_ms, response_size, retry_count,
                )
                return resp.json()

            except requests.exceptions.Timeout as exc:
                last_exc = exc
                if attempt == 0:
                    continue
                break

            except Exception as exc:  # noqa: BLE001 — catch-all to break retry loop on unexpected errors
                last_exc = exc
                break

        # All attempts exhausted
        latency_ms  = round((time.perf_counter() - t0) * 1000, 2)
        http_status = getattr(getattr(last_exc, "response", None), "status_code", None)
        is_timeout  = isinstance(last_exc, requests.exceptions.Timeout) or http_status == 408
        error_cat   = self.classify_error(last_exc, http_status)

        logger.error(
            "CDS request failed: path=%s publisher=%s latency_ms=%.2f http_status=%s "
            "retry=%d timeout=%s category=%s error=%s",
            path, publisher_id, latency_ms, http_status,
            retry_count, is_timeout, error_cat, last_exc, exc_info=True,
        )
        return self.normalize_error(last_exc, url)


# Module-level singleton — the shared CDS service object.
cds_client = CdsClient()
