# Responsibility: Verify Publive credentials against the CDS API.
import base64
import logging
import time

from django.conf import settings
import requests

from authentication.services.base import CredentialCheck

logger = logging.getLogger(__name__)


class CredentialsMixin:
    """Publive credential-verification helpers for the auth service."""

    def validate_cds_credentials(
        self,
        publisher_id: str,
        api_key: str,
        api_secret: str,
    ) -> tuple[bool, int]:
        """Call the Publive CDS API to verify credentials; return (is_valid, http_status).
        Raises requests.RequestException if the CDS is unreachable — callers must handle it.
        """
        token: str = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode()
        t0: float = time.perf_counter()
        base = settings.CDS_BASE_URL.format(publisher_id=publisher_id)
        resp = requests.get(
            f"{base}/",
            headers={"Authorization": f"Basic {token}"},
            timeout=10,
        )
        latency_ms: float = round((time.perf_counter() - t0) * 1000, 2)
        logger.info(
            "CDS validation: publisher=%s status=%d latency_ms=%.2f",
            publisher_id, resp.status_code, latency_ms,
        )
        return 200 <= resp.status_code < 300, resp.status_code

    def verify_publive_credentials(
        self,
        publisher_id: str,
        api_key: str,
        api_secret: str,
    ) -> CredentialCheck:
        """Run the shared credential-validation pipeline used by both the OAuth
        authorize and session-login flows: require all three fields, then verify
        them against the CDS API.

        Pure decision logic that never raises — CDS unreachability is reported as a
        cds_unreachable outcome rather than propagating requests.RequestException —
        so each caller can map the result onto its own telemetry and response shape.
        """
        if not all([publisher_id, api_key, api_secret]):
            return CredentialCheck(False, "missing_params")
        try:
            ok, status_code = self.validate_cds_credentials(publisher_id, api_key, api_secret)
        except requests.RequestException as exc:
            return CredentialCheck(False, "cds_unreachable", detail=str(exc), exc=exc)
        if not ok:
            return CredentialCheck(False, "cds_auth_failed", status_code=status_code)
        return CredentialCheck(True, status_code=status_code)
