# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run dev server
python manage.py runserver

# Apply migrations
python manage.py migrate

# Create new migration after model changes
python manage.py makemigrations

# Collect static files
python manage.py collectstatic --noinput

# Run tests (use the hermetic test settings — in-memory SQLite)
python manage.py test --settings=publive_mcp.settings_test

# Run a single test module / class / method
python manage.py test mcp.tests.test_validate_tool_args --settings=publive_mcp.settings_test
```

Tests live in `authentication/tests/` and `mcp/tests/` and are mock-only (no network, no external services). `publive_mcp/settings_test.py` overrides the database to in-memory SQLite and pins `CDS_BASE_URL`/`CMS_BASE_URL` to test hosts. External HTTP is patched at the import site (e.g. patch `mcp.cms.categories.cms_post`, `authentication.views.validate_cds_credentials`).

**Environment:** Configuration is driven entirely by one of three committed dotenv profiles — `dev.env`, `beta.env`, `prod.env` — selected by the `ENV_FILE` variable (default `dev.env`; `settings.py` calls `load_dotenv(BASE_DIR / ENV_FILE)`). There is no `IS_PRODUCTION` / `RAILWAY_ENVIRONMENT` / `DJANGO_ENV` conditional — every behavioural setting (`DEBUG`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, per-app log levels, base URLs) is defined explicitly in each profile. Run locally with the defaults in `dev.env` (SQLite, `DEBUG=True`). Secrets (`DJANGO_SECRET_KEY`, `CREDENTIALS_ENCRYPTION_KEYS`, `DATABASE_URL`) are placeholders in `beta.env`/`prod.env` and are injected via Railway's dashboard at runtime (real OS env vars win — `load_dotenv` does not override them).

**Deployment:** Docker image (`Dockerfile`, `python:3.12-slim`) deployed to Railway, run with gunicorn (see `entrypoint.sh`; transport is stateless `POST /mcp`, so no long-lived-stream thread tuning is needed). There is no `Procfile` / release phase — `collectstatic` runs at image build time, and `entrypoint.sh` runs `migrate --noinput` then execs gunicorn on every container start. See `docs/deployment.md` for details.

## Architecture

### MCP Protocol Layer (`mcp/views/` + `protocol/` + `transport/`)

`views/` is a thin routing layer only (`health_check`, `health_ready`, `mcp_endpoint`) — it authenticates via `protocol/auth.py` and immediately delegates to the transport/protocol module. No business logic lives there.

- **Transport** (`mcp/transport/`): `http.py` handles the single stateless Streamable HTTP transport — `POST /mcp` (single or batch JSON-RPC). `GET /mcp` returns 405. Malformed JSON returns a JSON-RPC `-32700` parse error. On non-`initialize` requests it validates the `MCP-Protocol-Version` header against `SUPPORTED_PROTOCOL_VERSIONS` (400 if unsupported; absent is treated as `2025-03-26` for back-compat). The `mcp_endpoint` router (`mcp/views/`) validates the `Origin` header via `authentication.services.check_origin` before auth (native clients send no Origin and are allowed).
- **Protocol** (`mcp/protocol/`): `dispatch.py`'s `dispatch_jsonrpc()` is the JSON-RPC router — handles `initialize`, `tools/list`, and `tools/call`, validates arguments against each tool's `inputSchema`, then routes to `dispatch_cds_tool()` or `dispatch_cms_tool()` by tool name. `initialize` negotiates the protocol version (`negotiate_protocol_version`): it echoes the client's requested `protocolVersion` when supported, else advertises `LATEST_PROTOCOL_VERSION` (`2025-06-18`). `auth.py` resolves credentials from either a Bearer token (DB lookup via `OAuthToken`) or a Django session cookie. `session.py` owns the protocol-version constants (`LATEST_PROTOCOL_VERSION`, `SUPPORTED_PROTOCOL_VERSIONS`, `DEFAULT_NEGOTIATED_PROTOCOL_VERSION`), derives a stable session id per request.

### Tool Layers

**`mcp/cds/`** — 22 read-only CDS tools, split across `authors.py`, `categories.py`, `content.py`, `posts.py`, `publisher.py`, `sitemaps.py`, `static_files.py`, `tags.py`. Each module exports `SCHEMAS` + `HANDLERS`; the package `__init__.py` aggregates them into `TOOLS` and dispatches via `dispatch_cds_tool()`. Each tool entry is a dict with `name`, `description`, `inputSchema`, and a `handler` callable that takes `(credentials, arguments)` and returns an MCP content list.

**`mcp/cms/`** — 39 CMS write tools, split across `categories.py`, `custom_components.py`, `custom_content_types.py`, `live_blog.py`, `media.py`, `posts.py`, `tags.py`, `validators.py` (plus `helpers.py` for shared dry-run/confirm preview formatters). Same `SCHEMAS`/`HANDLERS` pattern, aggregated into `CMS_TOOLS` and dispatched via `dispatch_cms_tool()`. Write operations follow a tiered safety model:
- **Tier 2 (create):** `dry_run=True` by default — returns a preview without writing.
- **Tier 3 (update):** `dry_run=True` shows a human-readable diff of old vs new fields.
- **Tier 3 (delete):** Requires both `dry_run=false` AND `confirm_delete=true` to execute.

### HTTP Clients (`mcp/clients/`)

**`clients/cds.py`** — `cds_get(credentials, path, params)`. Basic Auth, 5s timeout, 1 automatic retry on HTTP 408 or `requests.Timeout`.

**`clients/cms.py`** — `cms_get/post/patch/delete(credentials, path, ...)`. Basic Auth, 10s timeout, no retry. All functions return either the parsed JSON response or a normalized error dict with `error_type`, `message`, `retryable`.

**`clients/shared.py`** — shared `build_base_url()` and Basic Auth header helpers. Both clients derive the base URL as `https://{cds|cms}-beta.thepublive.com/publisher/{publisher_id}` (overridable via the `CDS_BASE_URL`/`CMS_BASE_URL` env vars) where `publisher_id` comes from credentials.

### Auth Layer (`authentication/`)

Two auth paths:
1. **OAuth 2.0 + PKCE** (`/register`, `/oauth/authorize`, `/oauth/token`): For API clients (Claude Desktop, Cursor). Issues `OAuthToken` records (no expiry — permanent until revoked or upserted) that are stored in the database and resolved by `views.py` on each tool call.
2. **Session auth** (`/connect`, `/auth/login`): Browser-based login that stores credentials in Django sessions (no self-expiry — `session_ttl_seconds = -1` and a 10-year cookie ceiling; ends only via explicit `/auth/logout`).

Both paths validate credentials against the CDS API before issuing tokens/sessions.

### Logging (`mcp/prompt_capture.py`)

Observability is via structured JSON logging only (configured in `publive_mcp/settings.py`); each tool call, auth event, and upstream request is logged with structured fields. There is no external APM agent.

`prompt_capture.py` exposes `strip_prompt_from_args`, which removes the client-supplied `_prompt` / `prompt` argument keys before the tool runs (they are a prompt side-channel, not tool inputs).

### Adding a New Tool

1. Add a handler function and a `SCHEMAS`/`HANDLERS` entry in the relevant module under `mcp/cds/` (CDS read) or `mcp/cms/` (CMS write).
2. The package `__init__.py` aggregates those into `TOOLS` / `CMS_TOOLS` automatically; each entry carries `name`, `description`, `inputSchema`.
3. No changes needed in `views.py` — dispatch is data-driven from those lists.

For CMS write tools, follow the dry_run/confirm pattern matching the tier of the operation.
