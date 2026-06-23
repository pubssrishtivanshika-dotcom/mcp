# Responsibility: Project settings. All environment-specific behaviour is loaded
# from a single dotenv profile (dev.env / beta.env / prod.env). The active profile
# is chosen by the ENV_FILE variable (default: dev.env) — that selector is the ONLY
# value read from the ambient OS environment; every other setting comes from the
# loaded profile. There is no environment-name conditional in this file.
# DJANGO_SETTINGS_MODULE=publive_mcp.settings resolves here.

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# ── Active environment profile ───────────────────────────────────────────────────
# Pick the dotenv profile to load. Local dev defaults to dev.env; Docker/Railway set
# ENV_FILE=beta.env or ENV_FILE=prod.env per deploy target. load_dotenv does NOT
# override variables already present in the OS environment, so real secrets injected
# by Railway's dashboard (DJANGO_SECRET_KEY, DATABASE_URL, CREDENTIALS_ENCRYPTION_KEYS)
# take precedence over the placeholders committed in the profile files.
ENV_FILE = os.environ.get("ENV_FILE", "dev.env")
load_dotenv(BASE_DIR / ENV_FILE)


def _env_bool(name: str, default: bool = False) -> bool:
    """Parse a boolean from the environment ('1'/'true'/'yes'/'on' → True)."""
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")

# ALLOWED_HOSTS comes from DJANGO_ALLOWED_HOSTS (comma-separated, e.g.
# "mcp.thepublive.com,api.thepublive.com"). Railway's auto-injected public domain
# is appended when present. An empty list falls back to "*" (the dev profile leaves
# it empty; beta/prod profiles must list real hosts).
_allowed_hosts = [
    h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()
]
_railway_host = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
if _railway_host:
    _allowed_hosts.append(_railway_host)
# Railway probes the app via GET / with Host "healthcheck.railway.app" during
# deploys; allow it so the healthcheck doesn't 400 (only matters when a real
# allow-list is configured — the empty dev profile already falls back to "*").
if _allowed_hosts:
    _allowed_hosts.append("healthcheck.railway.app")
ALLOWED_HOSTS = _allowed_hosts or ["*"]

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")

# Security-sensitive toggles — set explicitly per profile (no env-name conditional).
DEBUG = _env_bool("DEBUG")
SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE")

# Fernet key(s) for encrypting Publive API credentials at rest (OAuthCode/OAuthToken
# rows and DB-backed sessions). Comma-separated for rotation — the first key encrypts,
# all keys can decrypt. When unset, a key is derived from DJANGO_SECRET_KEY so
# credentials are never stored in plaintext; provision a dedicated key in production.
CREDENTIALS_ENCRYPTION_KEYS = os.environ.get("CREDENTIALS_ENCRYPTION_KEYS", "")

# OAuth 2.0 access-token lifetime (seconds). Access tokens expire after this
# window; clients obtain a fresh one via the refresh_token grant, which rotates
# both the access token and the refresh token. Default: 1 hour.
OAUTH_ACCESS_TOKEN_TTL_SECONDS = int(
    os.environ.get("OAUTH_ACCESS_TOKEN_TTL_SECONDS", "3600")
)

# Server version advertised in the MCP `initialize` serverInfo and health probes.
SERVER_VERSION = os.environ.get("SERVER_VERSION", "1.0.0")

# Upstream API base URLs — required per profile (no hardcoded host fallback).
CDS_BASE_URL = os.environ.get("CDS_BASE_URL", "")
CMS_BASE_URL = os.environ.get("CMS_BASE_URL", "")

# /*
#     Apps - self-contained module that implements a specific feature
#     Middleware - runs for every request and response, checkpoints before and after your views.
# */

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "authentication",
    "mcp",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "mcp.middleware.RequestIDMiddleware",
    "mcp.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "publive_mcp.urls"


# ### #
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
            ],
        },
    },
]

WSGI_APPLICATION = "publive_mcp.wsgi.application"


DATABASES = {
    "default": dj_database_url.config(conn_max_age=600)
}


# ── Sessions ──────────────────────────────────────────────────────────────────

# Sessions stored in Postgres (via DATABASE_URL on Railway) so they survive redeploys.
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 10 * 365 * 24 * 3600
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_SAVE_EVERY_REQUEST = True


# ── CSRF ──────────────────────────────────────────────────────────────────────
# CsrfViewMiddleware (registered above) protects browser form POSTs such as the
# OAuth authorize page; the {% csrf_token %} tag in authorize.html supplies the
# token. The CSRF cookie is read by JS only via the rendered token, so it stays
# HttpOnly. Secure-only over HTTPS (set per profile); Lax matches the session cookie.
CSRF_COOKIE_SECURE = _env_bool("CSRF_COOKIE_SECURE")
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"

# On HTTPS Django checks the request Origin against the host. Behind Railway's
# TLS-terminating proxy the request scheme can read as http internally, so the
# public https origin(s) must be listed explicitly. Derived from BASE_URL and
# the configured ALLOWED_HOSTS.
CSRF_TRUSTED_ORIGINS = list(
    dict.fromkeys(
        [BASE_URL.rstrip("/")] + [f"https://{host}" for host in _allowed_hosts]
    )
)


# ── OAuth security ────────────────────────────────────────────────────────────
# The CORS Origin allowlist is the single source of truth in the database
# (authentication.AllowedOrigin). The table is seeded on first migration (authentication
# migration 0003) and managed at runtime in the DB — add/remove clients there,
# never in settings. See authentication.services.AuthService.get_allowed_origins.

# Dynamic client registration (RFC 7591 / OAuth 2.1) is open to any client —
# redirect_uri just has to be https:// or a loopback address. See
# authentication.services.AuthService.is_registrable_redirect_uri.

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Structured JSON logging ───────────────────────────────────────────────────
# Emits each log line as JSON so a log aggregator can index individual fields.


# ###### #
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": os.environ.get("ROOT_LOG_LEVEL", "INFO"),
    },
    "loggers": {
        # Per-app log levels — set explicitly per profile (no env-name conditional).
        "django": {
            "handlers": ["console"],
            "level": os.environ.get("DJANGO_LOG_LEVEL", "WARNING"),
            "propagate": False,
        },
        "mcp": {
            "handlers": ["console"],
            "level": os.environ.get("MCP_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
        "authentication": {
            "handlers": ["console"],
            "level": os.environ.get("AUTH_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
    },
}
