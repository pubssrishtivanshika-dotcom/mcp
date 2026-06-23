# Responsibility: Symmetric encryption of Publive API credentials at rest (Fernet),
# plus the Django model field that applies it transparently to a credentials column.

import base64
import hashlib
import json
import logging
from typing import Optional, Union

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.db import models

logger = logging.getLogger(__name__)


def _configured_keys() -> list[bytes]:
    """Return explicitly-provisioned Fernet keys from settings."""
    raw = getattr(settings, "CREDENTIALS_ENCRYPTION_KEYS", None)
    if not raw:
        return []
    parts = raw.split(",") if isinstance(raw, str) else [str(p) for p in raw]
    return [p.strip().encode() for p in parts if p and p.strip()]


def _derive_key_from_secret(secret: str) -> bytes:
    """Derive a stable Fernet key from DJANGO_SECRET_KEY. """
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _get_cipher() -> MultiFernet:
    """ Build a rotation-aware cipher. The first configured key encrypts; every configured key can decrypt, enabling zero-downtime key rotation (add the new key first, re-encrypt, drop the old key). Falls back to a key derived from SECRET_KEY when none is configured. """
    keys = _configured_keys() or [_derive_key_from_secret(settings.SECRET_KEY)]
    return MultiFernet([Fernet(k) for k in keys])


def encrypt_credentials(credentials: dict) -> str:
    """Encrypt a credentials dict into an opaque Fernet token (ascii text)."""
    payload = json.dumps(credentials, separators=(",", ":")).encode("utf-8")
    return _get_cipher().encrypt(payload).decode("ascii")


def decrypt_credentials(value: Union[str, bytes, dict, None]) -> Optional[dict]:
    """Decrypt a Fernet token back into a credentials dict."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    value_bytes = value.encode("utf-8") if isinstance(value, str) else value
    try:
        return json.loads(_get_cipher().decrypt(value_bytes).decode("utf-8"))
    except InvalidToken:
        try:
            decoded = json.loads(value_bytes.decode("utf-8"))
        except (ValueError, TypeError):
            decoded = None
        if isinstance(decoded, dict):
            logger.warning("decrypt_credentials: read legacy plaintext credentials")
            return decoded
        raise InvalidToken


class EncryptedCredentialsField(models.TextField):
    """A dict field whose JSON value is Fernet-encrypted in the database."""

    description = "Fernet-encrypted JSON credentials"

    def from_db_value(self, value, expression, connection):
        return decrypt_credentials(value)

    def to_python(self, value):
        if value is None or isinstance(value, dict):
            return value
        return decrypt_credentials(value)

    def get_prep_value(self, value):
        if value is None or isinstance(value, str):
            # str is treated as already-ciphertext (e.g. a raw queryset .update()).
            return value
        return encrypt_credentials(value)
