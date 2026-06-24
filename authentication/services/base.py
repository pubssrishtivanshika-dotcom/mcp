# Responsibility: Shared value types for the auth service helpers.
from typing import Optional, NamedTuple


class CredentialCheck(NamedTuple):
    """Outcome of verifying Publive credentials against the CDS API."""

    ok: bool
    failure_reason: Optional[str] = None
    status_code: Optional[int] = None
    detail: Optional[str] = None
    exc: Optional[BaseException] = None
