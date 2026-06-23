#!/bin/sh

echo "[entrypoint] DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE}"
echo "[entrypoint] ENV_FILE=${ENV_FILE:-dev.env (default)}"
echo "[entrypoint] applying migrations..."
python manage.py migrate --noinput 2>&1 || echo "[entrypoint] !!! migrate FAILED — see error above"

echo "[entrypoint] authentication migration status:"
python manage.py showmigrations authentication 2>&1 || true

echo "[entrypoint] starting gunicorn on port ${PORT:-8000}"

# Wrap gunicorn with the New Relic agent only when a license key is present.
# Without a key (e.g. local dev) we run gunicorn directly.
NR_PREFIX=""
if [ -n "${NEW_RELIC_LICENSE_KEY}" ]; then
    export NEW_RELIC_CONFIG_FILE="${NEW_RELIC_CONFIG_FILE:-/app/newrelic.ini}"
    echo "[entrypoint] New Relic license key detected — starting agent (config: ${NEW_RELIC_CONFIG_FILE})"
    NR_PREFIX="newrelic-admin run-program"
else
    echo "[entrypoint] NEW_RELIC_LICENSE_KEY not set — running without New Relic"
fi

exec ${NR_PREFIX} gunicorn publive_mcp.wsgi \
    -b 0.0.0.0:"${PORT:-8000}" \
    --timeout 60 \
    --access-logfile -
