# Responsibility: OAuthClient model + manager — dynamically-registered OAuth clients.
from __future__ import annotations

from django.db import models


class OAuthClientManager(models.Manager):
    """Query/create helpers for OAuthClient — the single entry point for OAuthClient access."""

    def create_client(self, *, client_id: str, redirect_uri: str = "") -> "OAuthClient":
        """Register a new OAuth client."""
        return self.create(client_id=client_id, redirect_uri=redirect_uri)

    def get_by_client_id(self, client_id: str | None) -> "OAuthClient | None":
        """Return the client for ``client_id``, or None if unknown."""
        if not client_id:
            return None
        try:
            return self.get(client_id=client_id)
        except self.model.DoesNotExist:
            return None


class OAuthClient(models.Model):
    """
    A dynamically-registered OAuth 2.0 client (one per AI client install).
    """

    client_id    = models.CharField(max_length=64, unique=True, db_index=True)
    redirect_uri = models.CharField(max_length=512, blank=True, default="")
    created_at   = models.DateTimeField(auto_now_add=True)

    objects = OAuthClientManager()

    class Meta:
        db_table = "oauth_client"
        ordering = ["-created_at"]
        verbose_name = "OAuth Client"
        verbose_name_plural = "OAuth Clients"
