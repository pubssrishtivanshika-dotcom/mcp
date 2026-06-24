# Responsibility: Session credential storage/retrieval and absolute-TTL enforcement.
import logging
import time
from typing import Optional

from cryptography.fernet import InvalidToken

from authentication.crypto import decrypt_credentials, encrypt_credentials

logger = logging.getLogger(__name__)


class SessionMixin:
    """Session-backed credential helpers for the auth service."""

    def get_session_credentials(self, session) -> Optional[dict]:
        """Return the credentials dict stored in the session, or None if absent.

        Credentials are encrypted at rest in the DB-backed session (see
        set_session_credentials); decryption is tolerant of legacy plaintext sessions.
        """
        raw = session.get("credentials")
        if raw is None:
            return None
        try:
            creds = decrypt_credentials(raw)
        except InvalidToken:
            logger.warning("get_session_credentials: undecryptable session credentials")
            return None
        return creds if isinstance(creds, dict) else None

    def set_session_credentials(self, session, credentials: dict) -> None:
        """Store credentials in the session, encrypted at rest."""
        session["credentials"] = encrypt_credentials(credentials)

    def check_session_ttl(self, session) -> bool:
        """Return True if the session has exceeded its original TTL.


        Django's rolling SESSION_SAVE_EVERY_REQUEST is intentionally disabled so
        these stored values are the authoritative expiry source.
        """
        ttl_seconds = session.get("session_ttl_seconds", -1)
        if ttl_seconds <= 0:
            return False
        created_at_ts = session.get("session_created_at")
        if not created_at_ts:
            return False
        try:
            deadline_ts = int(created_at_ts) + int(ttl_seconds)
            return time.time() > deadline_ts
        except (ValueError, TypeError):
            return False
