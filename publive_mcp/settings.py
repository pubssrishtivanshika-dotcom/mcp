import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent



ENV_FILE = os.environ.get("ENV_FILE", "dev.env")
load_dotenv(BASE_DIR / ENV_FILE)


def _env_bool(name: str, default: bool = False) -> bool:
    """Parse a boolean from the environment ('1'/'true'/'yes'/'on' → True)."""
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")


_allowed_hosts = [
    h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()
]
_railway_host = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()


# Updating the ALLOWED_HOSTS list for Railway 
if _railway_host:
    _allowed_hosts.append(_railway_host)
if _allowed_hosts:
    _allowed_hosts.append("healthcheck.railway.app")


ALLOWED_HOSTS = _allowed_hosts or ["*"]

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")


DEBUG = _env_bool("DEBUG")
SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE")


CREDENTIALS_ENCRYPTION_KEYS = os.environ.get("CREDENTIALS_ENCRYPTION_KEYS", "")


OAUTH_ACCESS_TOKEN_TTL_SECONDS = int(
    os.environ.get("OAUTH_ACCESS_TOKEN_TTL_SECONDS", "3600")
)


SERVER_VERSION = os.environ.get("SERVER_VERSION", "1.0.0")


CDS_BASE_URL = os.environ.get("CDS_BASE_URL", "")
CMS_BASE_URL = os.environ.get("CMS_BASE_URL", "")


INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "corsheaders",
    "authentication",
    "mcp",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
]

ROOT_URLCONF = "publive_mcp.urls"

CORS_ALLOWED_ORIGINS: list[str] = []


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

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 10 * 365 * 24 * 3600
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_SAVE_EVERY_REQUEST = True


CSRF_COOKIE_SECURE = _env_bool("CSRF_COOKIE_SECURE")
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"


CSRF_TRUSTED_ORIGINS = list(
    dict.fromkeys(
        [BASE_URL.rstrip("/")] + [f"https://{host}" for host in _allowed_hosts]
    )
)


STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


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
