# Data migration: seed the AllowedOrigin CORS allowlist with the web-based AI
# clients the MCP server is meant to serve (Claude, ChatGPT, Gemini).
#
# The table is the single source of truth for check_origin (see
# authentication.services.AuthService.get_allowed_origins). It ships empty from
# 0001_initial, and check_origin fails closed — so without this seed every
# browser-based client is blocked until a row is added by hand. Desktop clients
# send no Origin and are unaffected either way.
#
# Origins are managed at runtime in the DB after this; edit rows there rather
# than amending this migration. Add/remove entries below only to change the
# out-of-the-box default. Stored without a trailing slash to match the
# normalization in get_allowed_origins (which rstrips "/").
from django.db import migrations

# (origin, label) — keep origins scheme + host only, no trailing slash, no path.
SEED_ORIGINS = [
    ("https://claude.ai",         "Claude (web)"),
    ("https://chatgpt.com",       "ChatGPT (web)"),
    ("https://chat.openai.com",   "ChatGPT (web, legacy domain)"),
    ("https://gemini.google.com", "Gemini (web)"),
]


def seed_allowed_origins(apps, schema_editor):
    AllowedOrigin = apps.get_model("authentication", "AllowedOrigin")
    for origin, label in SEED_ORIGINS:
        # Idempotent: safe to run after manual inserts; never overwrites an
        # operator's runtime edits to an existing row (e.g. is_active toggles).
        AllowedOrigin.objects.get_or_create(
            origin=origin,
            defaults={"label": label, "is_active": True},
        )


def unseed_allowed_origins(apps, schema_editor):
    AllowedOrigin = apps.get_model("authentication", "AllowedOrigin")
    AllowedOrigin.objects.filter(
        origin__in=[origin for origin, _ in SEED_ORIGINS]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_allowed_origins, unseed_allowed_origins),
    ]
