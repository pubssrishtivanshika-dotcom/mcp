#!/bin/sh

echo "[entrypoint] DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE}"
echo "[entrypoint] ENV_FILE=${ENV_FILE:-dev.env (default)}"

# On AWS ECS/Fargate the ALB health check hits "GET /" with the Host header set to
# the task's private IP. Django's ALLOWED_HOSTS lists real hostnames only, so that
# request would 400 and the task would be marked unhealthy. Discover the task IP from
# the ECS container-metadata endpoint and append it to DJANGO_ALLOWED_HOSTS.
# (No-op outside ECS, where ECS_CONTAINER_METADATA_URI_V4 is unset.)
if [ -n "${ECS_CONTAINER_METADATA_URI_V4}" ]; then
    TASK_IP=$(python -c "import json,os,urllib.request; \
url=os.environ['ECS_CONTAINER_METADATA_URI_V4']+'/task'; \
data=json.load(urllib.request.urlopen(url, timeout=2)); \
print(next(n['IPv4Addresses'][0] for c in data['Containers'] for n in c.get('Networks', []) if n.get('IPv4Addresses')))" 2>/dev/null)
    if [ -n "${TASK_IP}" ]; then
        export DJANGO_ALLOWED_HOSTS="${DJANGO_ALLOWED_HOSTS:+${DJANGO_ALLOWED_HOSTS},}${TASK_IP}"
        echo "[entrypoint] ECS task IP ${TASK_IP} appended to DJANGO_ALLOWED_HOSTS"
    else
        echo "[entrypoint] !!! could not resolve ECS task IP — ALB health checks may 400"
    fi
fi

echo "[entrypoint] applying migrations..."
python manage.py migrate --noinput 2>&1 || echo "[entrypoint] !!! migrate FAILED — see error above"

echo "[entrypoint] authentication migration status:"
python manage.py showmigrations authentication 2>&1 || true

echo "[entrypoint] starting gunicorn on port ${PORT:-8000}"


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
