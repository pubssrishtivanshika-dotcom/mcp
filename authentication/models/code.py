# Responsibility: OAuthCode model + manager — single-use PKCE authorization codes.
from __future__ import annotations

from django.db import models

from authentication.crypto import EncryptedCredentialsField


class OAuthCodeManager(models.Manager):
    """Query/create helpers for OAuthCode — the single entry point for auth-code access.

    Codes are single-use and short-lived; lookups are never cached (a cached hit
    after the row was consumed would re-validate a spent code).
    """

    def create_code(
        self,
        *,
        code: str,
        client_id: str,
        redirect_uri: str,
        code_challenge: str,
        credentials: dict,
        expires_at,
    ) -> "OAuthCode":
        """Issue a single-use PKCE authorization code."""
        return self.create(
            code=code,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            credentials=credentials,
            expires_at=expires_at,
        )

    def get_by_code(self, code: str) -> "OAuthCode | None":
        """Return the auth code for ``code``, or None if unknown."""
        try:
            return self.get(code=code)
        except self.model.DoesNotExist:
            return None


class OAuthCode(models.Model):
    """Single-use PKCE authorization code. Valid for 10 minutes, deleted on exchange."""

    code           = models.CharField(max_length=128, unique=True)
    client_id      = models.CharField(max_length=64, db_index=True)
    redirect_uri   = models.TextField()
    code_challenge = models.CharField(max_length=256)
    credentials    = EncryptedCredentialsField()
    expires_at     = models.DateTimeField()

    objects = OAuthCodeManager()

    class Meta:
        db_table = "oauth_code"
        ordering = ["-expires_at"]
        verbose_name = "OAuth Code"
        verbose_name_plural = "OAuth Codes"
