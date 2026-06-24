# Responsibility: AllowedOrigin model — CORS allowlist for the OAuth/MCP endpoints.
from __future__ import annotations

from django.db import models


class AllowedOrigin(models.Model):
    """
    A browser Origin permitted to call the OAuth/MCP endpoints (CORS allowlist).

    Web-based AI clients (Claude, ChatGPT, Gemini, …) send an Origin header that
    must match an active row here. Desktop clients send no Origin and bypass this
    check. Initial rows are seeded by data migration 0002_seed_allowed_origins;
    thereafter rows are managed directly in the database (e.g. via `manage.py shell`),
    and changes take effect immediately since the table is read directly on each request.
    """

    origin     = models.CharField(max_length=255, unique=True, db_index=True)
    label      = models.CharField(max_length=128, blank=True, default="")
    is_active  = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "allowed_origin"
        ordering = ["origin"]
        verbose_name = "Allowed Origin"
        verbose_name_plural = "Allowed Origins"

    def __str__(self) -> str:
        return self.origin
