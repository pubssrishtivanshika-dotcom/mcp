FROM python:3.12-slim

# Prevents Python from writing .pyc files and ensures stdout/stderr are unbuffered
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies required by psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*
    # package metadata & cache remove

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ARG DJANGO_SECRET_KEY=build-time-placeholder-not-used-at-runtime
ENV DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}
ENV DJANGO_SETTINGS_MODULE=publive_mcp.settings
# Default dotenv profile for the image (the safe, non-debug one). Each Railway
# environment overrides this in its dashboard variables, e.g. ENV_FILE=beta.env for
# the beta environment, ENV_FILE=prod.env for production.
ENV ENV_FILE=prod.env

# Collect static files at build time
RUN python manage.py collectstatic --noinput

# Makes script executable
RUN chmod +x /app/entrypoint.sh

# Run as an unprivileged user. Create it and hand over ownership of the app dir
# (so the runtime user can read the code/static and write any local state) before
# dropping privileges for the container's lifetime.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["/app/entrypoint.sh"]
