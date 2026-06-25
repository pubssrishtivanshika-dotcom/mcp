#!/bin/sh

python manage.py migrate --noinput

exec newrelic-admin run-program gunicorn publive_mcp.wsgi \
    -b 0.0.0.0:"${PORT:-8000}" --timeout 60 --access-logfile -
