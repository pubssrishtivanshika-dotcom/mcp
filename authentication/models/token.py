# Responsibility: OAuthToken model + manager — bearer tokens issued after PKCE auth.
from __future__ import annotations

from django.db import models
from django.utils import timezone

from authentication.crypto import EncryptedCredentialsField


class OAuthTokenManager(models.Manager):
    """Query/create/revoke helpers for OAuthToken — the single entry point for token access.

    Deliberately uncached: tokens are rotated (refresh grant), revoked (RFC 7009),
    and expire by clock, so a cached row would keep a revoked/rotated/expired token
    working until the TTL lapsed — a security-staleness bug. Every lookup hits the
    DB by indexed unique column, which is already cheap.
    """

    def create_token(
        self,
        *,
        token: str,
        credentials: dict,
        client_id: str = "",
        publisher_id: str = "",
        refresh_token: str | None = None,
        expires_at=None,
    ) -> "OAuthToken":
        """Issue a new bearer token."""
        return self.create(
            token=token,
            client_id=client_id,
            publisher_id=publisher_id,
            refresh_token=refresh_token,
            credentials=credentials,
            expires_at=expires_at,
        )

    def get_by_token(self, token: str) -> "OAuthToken | None":
        """Return the token row for the access ``token`` value, or None if unknown."""
        try:
            return self.get(token=token)
        except self.model.DoesNotExist:
            return None

    def get_for_update_by_refresh_token(self, refresh_token: str) -> "OAuthToken | None":
        """Row-lock and return the token for ``refresh_token`` (must run inside a transaction)."""
        try:
            return self.select_for_update().get(refresh_token=refresh_token)
        except self.model.DoesNotExist:
            return None

    def get_active_token(self, client_id: str, publisher_id: str) -> "OAuthToken | None":
        """Return the existing token row for this client+publisher (stable-identity upsert), or None.

        Returns the row regardless of its expiry — the OAuth code grant re-uses the
        same access-token identity and refreshes the expiry on re-authorisation.
        """
        return self.filter(client_id=client_id, publisher_id=publisher_id).first()

    def revoke(self, token_value: str, *, prefer_refresh: bool = False) -> bool:
        """Delete the row matching ``token_value`` by access or refresh token (RFC 7009).

        ``prefer_refresh`` tries the refresh_token column first (when the caller's
        token_type_hint says so); either way both columns are attempted. Returns
        True if a row was deleted.
        """
        first, second = ("refresh_token", "token") if prefer_refresh else ("token", "refresh_token")
        deleted, _ = self.filter(**{first: token_value}).delete()
        if not deleted:
            deleted, _ = self.filter(**{second: token_value}).delete()
        return bool(deleted)


class OAuthToken(models.Model):
    """
    Bearer token issued after successful PKCE auth.

    The access ``token`` expires at ``expires_at``; clients obtain a fresh one via
    the refresh_token grant, which rotates both the access token and the refresh
    token. ``refresh_token`` itself does not self-expire (it is invalidated only by
    rotation or revocation). ``expires_at`` is nullable so tokens issued before this
    field existed are treated as non-expiring until their next refresh.
    credentials stores {publisherId, apiKey, apiSecret} — the Publive API credentials
    """

    token         = models.CharField(max_length=128, unique=True)
    client_id     = models.CharField(max_length=64, db_index=True, blank=True, default="")
    publisher_id  = models.CharField(max_length=64, db_index=True, blank=True, default="")
    refresh_token = models.CharField(max_length=128, unique=True, null=True, blank=True)
    credentials   = EncryptedCredentialsField()
    created_at    = models.DateTimeField(auto_now_add=True, null=True)
    expires_at    = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = OAuthTokenManager()

    class Meta:
        db_table = "oauth_token"
        ordering = ["-created_at"]
        verbose_name = "OAuth Token"
        verbose_name_plural = "OAuth Tokens"

    def is_expired(self) -> bool:
        """True when the access token has a set expiry that is in the past."""
        return self.expires_at is not None and self.expires_at <= timezone.now()
