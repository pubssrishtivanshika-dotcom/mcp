---
name: add-tool
description: >
  Use this skill when the user asks to "add a tool", "create a new tool",
  "add a CDS tool", "add a CMS tool", "add a read tool", "add a write tool",
  "implement a new MCP tool", "register a tool", or wants to expose a new
  Publive API endpoint as an MCP tool.
version: 3.0.0
---

# Adding MCP Tools to the Publive MCP Server

Tools are **fully data-driven**. No changes to `views.py`, `protocol/`, or `transport/` are ever needed. A tool is a method on a `ToolModule` subclass, decorated with `@tool(...)`, which carries that tool's MCP schema. The module instantiates the class once and calls `.build()` — that derives the `SCHEMAS` list and `HANDLERS` mapping the package `__init__.py` aggregates. Schema and handler live together on one method; there is no separate hand-maintained `SCHEMAS` list or `HANDLERS` dict.

---

## Architecture Snapshot

```
mcp/
  tool_registry.py         ← ToolModule base + @tool decorator + PAGINATION_PROPERTIES
                              ToolModule.build() → (SCHEMAS, HANDLERS) in definition order
                              ToolModule.list_resource() / get_resource() — shared read one-liners
  cds/                     ← read-only delivery tools (public content), client = cds_client
    posts.py               ← fetch_published_posts, fetch_published_post, fetch_post_by_url …
    categories.py          ← fetch_published_categories, fetch_published_category
    tags.py                ← fetch_published_tags, fetch_published_tag
    authors.py             ← fetch_authors, fetch_author
    publisher.py           ← fetch_publisher_profile, fetch_site_navigation, fetch_site_footer, fetch_newsletter_groups
    content.py             ← resolve_url_to_content_type, fetch_ad_slots, fetch_content_type_definitions, fetch_form_schema
    sitemaps.py            ← fetch_sitemap, fetch_sitemap_page
    static_files.py        ← fetch_static_file
    __init__.py            ← assembles TOOLS list + _HANDLER_REGISTRY + dispatch_cds_tool()
  cms/
    helpers.py             ← CmsToolModule (client = cms_client; create_resource / update_resource /
                              delete_resource), preview_create_op / preview_update_op / preview_delete_op,
                              DELETION_REQUIRES_CONFIRMATION, validate_live_blog_post_type, format_field_value
    categories.py          ← list/get_editorial_category, create/update/delete_category
    tags.py                ← list/get_editorial_tag, create/update/delete_tag
    posts.py               ← list/get_editorial_post, create_post, update_post, delete_post
    live_blog.py           ← list_editorial_liveblog_updates, get/add/update/delete_liveblog_update (nested paths)
    media.py               ← list_media_assets, get/register/update/delete_media_asset
    custom_components.py   ← list/get/create/update/delete_component_schema
    custom_content_types.py← list/get/create/update/delete_content_type_schema
    validators.py          ← validate_media_asset, validate_category, validate_author …
    newsletter.py          ← subscribe_newsletter, unsubscribe_newsletter, verify_newsletter_subscriber_email
    reader.py              ← login_reader, register_reader, forgot_password_reader, reset_password_reader, verify_reader_email
    __init__.py            ← assembles CMS_TOOLS + CMS_TOOL_NAMES + dispatch_cms_tool()
  clients/
    cds.py                 ← cds_client (CdsClient): .get(credentials, path, params), .is_not_found(result)
    cms.py                 ← cms_client (CmsClient): .get / .post / .patch / .delete
    shared.py              ← BaseHttpClient, build_base_url, REAUTH_HINT
```

### Intentionally excluded (do not re-scaffold)

- `submit_form` — removed: required a browser reCAPTCHA token, unusable in MCP (noted in `mcp/cms/__init__.py`).
- `reader/logout` — no backend call (token cleanup is client-side), nothing for a tool to do (noted in `mcp/cms/reader.py` docstring).

---

## Decision Tree

```
New tool request
│
├── Is it read-only (list, get, search, identify)?
│   ├── Uses public CDS API → mcp/cds/{domain}.py, subclass ToolModule, client = cds_client
│   └── Uses private CMS API (drafts, management) → mcp/cms/{domain}.py
│       subclass ToolModule (NOT CmsToolModule — that's for writes), use self.client.get
│
└── Is it a write operation (create, update, delete)?
    └── Always → mcp/cms/{domain}.py, subclass CmsToolModule
        ├── create  → self.create_resource(...)  (dry_run=True preview, dry_run=False POST)
        ├── update  → self.update_resource(...)   (dry_run=True diff,    dry_run=False PATCH)
        └── delete  → self.delete_resource(...)   (dry_run=True preview, dry_run=False + confirm_delete=True DELETE)

Domain file?
├── Tool belongs to an existing domain (posts, categories, tags…) → add a method to that class
└── Entirely new resource → create mcp/cds/newdomain.py (or cms/newdomain.py) with its own
    ToolModule/CmsToolModule subclass, then import its SCHEMAS/HANDLERS in __init__.py
```

---

## Naming Rules

| Tool type | Convention | Examples |
|---|---|---|
| Delivery (CDS read) | `fetch_noun` / `resolve_verb` | `fetch_published_posts`, `fetch_author`, `fetch_trending_posts` |
| Editorial list/get | `list_editorial_noun` / `get_editorial_noun` | `list_editorial_categories`, `get_editorial_post` |
| Editorial create/update/delete | `verb_noun` | `create_category`, `update_post`, `delete_tag` |
| Validation (pre-flight, no side effects) | `validate_noun` | `validate_media_asset`, `validate_category` |

The handler **method name** and the `@tool(name=...)` value don't have to match, but keep them aligned for readability (the codebase does).

---

## Step 1 — Add the `@tool`-decorated handler method

Add a method to the domain's `ToolModule`/`CmsToolModule` subclass, decorated with `@tool(...)`. The decorator carries `name`, `description`, and `inputSchema`; `build()` collects it automatically.

```python
@tool(
    name="tool_name",
    description="...",            # see description rules below
    inputSchema={
        "type": "object",
        "required": ["id"],      # omit the key entirely if nothing is required
        "properties": {
            "id":      {"type": "integer", "description": "Resource ID"},
            **PAGINATION_PROPERTIES,   # spreads page + limit; use for paginated list_* tools
            "dry_run": {"type": "boolean", "description": "true = preview only, no changes (default); false = execute"},
        },
    },
)
def tool_name(self, credentials: dict, args: dict):
    ...
```

`PAGINATION_PROPERTIES` (from `mcp.tool_registry`) is the shared `{page, limit}` fragment — spread it in rather than re-typing the two properties.

### Description rules

| Tool tier | What to include in description |
|---|---|
| CDS list | What is returned, key filter capabilities, when to prefer this over a CMS equivalent |
| CDS get | What is returned, when to prefer CMS version instead |
| CMS list/get | Same as CDS + note it includes drafts/unpublished |
| CMS create | List all immutable fields; state dry_run preview behaviour; "BEFORE calling" confirmation requirement |
| CMS update | List immutable fields; state dry_run diff behaviour; any special status gates (publish, draft bypass) |
| CMS delete | "CANNOT be undone"; downstream impact (orphaned references); dry_run=true + confirm_delete=true requirement |
| Validation | "Validation check — no changes made." + what {valid:true} and {valid:false} look like |

---

## Step 2 — Write the handler body

The handler is a method `(self, credentials, args)`. Reach the HTTP client via `self.client` (set on the class) or import the singleton directly. Keep handlers focused on the API call and response shaping — the shared base methods cover the mechanical cases.

### CDS read — paginated list (use the shared one-liner)

```python
class WidgetsTools(ToolModule):
    client = cds_client

    @tool(name="list_widgets", description="…", inputSchema={
        "type": "object", "properties": {**PAGINATION_PROPERTIES}})
    def list_widgets(self, credentials: dict, args: dict):
        return self.list_resource(credentials, args, path="/widgets/")
```

### CDS read — get by ID/slug (shared one-liner)

```python
_path_for = "/widget/{}/".format   # module-level

def get_widget(self, credentials: dict, args: dict):
    return self.get_resource(credentials, args, path_for=_path_for)
    # id_key defaults to "id"; pass id_key="identifier" / "filename" where the arg differs
```

### CDS read — get with input validation + not-found shaping

Use when the field has a strict format (e.g. numeric-only IDs) or you want a friendly 404.

```python
def fetch_widget(self, credentials: dict, args: dict):
    identifier = str(args.get("identifier", "")).strip()
    if not identifier:
        return {"error": "invalid_input", "message": "identifier is required."}
    if not identifier.isdigit():
        return {"error": "invalid_input",
                "message": f"identifier must be a numeric ID, got {identifier!r}."}
    result = cds_client.get(credentials, f"/widget/{identifier}/")
    if isinstance(result, dict) and cds_client.is_not_found(result):
        return {"error": "not_found", "message": f"Widget {identifier} was not found."}
    return result
```

### CMS tier 1 — list / get (no dry_run; subclass ToolModule, not CmsToolModule)

```python
class CmsWidgetsTools(ToolModule):
    client = cms_client

    def list_editorial_widgets(self, credentials, args):
        return self.list_resource(credentials, args, path="/widget/")

    def get_editorial_widget(self, credentials, args):
        return self.get_resource(credentials, args, path_for="/widget/{}/".format)
```

### CMS tier 2 — create (subclass CmsToolModule → one-liner)

```python
class CmsWidgetsTools(CmsToolModule):   # client = cms_client comes from the base
    def create_widget(self, credentials: dict, args: dict):
        return self.create_resource(credentials, args, resource="Widget", path="/widget/")
```

### CMS tier 3 — update (one-liner)

```python
    def update_widget(self, credentials: dict, args: dict):
        return self.update_resource(credentials, args, resource="Widget",
                                    path_for="/widget/{}/".format)
```

### CMS tier 3 — delete (one-liner, double-gate enforced by the base)

```python
    def delete_widget(self, credentials: dict, args: dict):
        return self.delete_resource(
            credentials, args, resource="Widget", path_for="/widget/{}/".format,
            warning="Posts referencing this widget will lose their association.")
```

`create_resource` / `update_resource` / `delete_resource` (on `CmsToolModule`) own the whole dry_run/confirm flow — preview formatting, fetching current state for the diff, propagating client errors, and the `dry_run=false AND confirm_delete=true` gate. Only drop to a hand-written body for non-standard flows (nested paths, publish gates, payload coercion) — see `references/tool-patterns.md`.

### Validation tool (read-only pre-flight check; subclass ToolModule)

```python
def validate_widget(self, credentials: dict, args: dict):
    result = cms_client.get(credentials, f"/widget/{args['id']}/")
    if "error_type" in result:
        return {"valid": False, "reason": f"Widget ID {args['id']} not found."}
    return {"valid": True, "id": args["id"], "name": result.get("name")}
```

---

## Step 3 — Build SCHEMAS/HANDLERS at the bottom of the module

There is **no hand-maintained `HANDLERS` dict**. Instantiate the class once and call `.build()`:

```python
widgets_tools = WidgetsTools()
SCHEMAS, HANDLERS = widgets_tools.build()
```

`build()` walks the class body in definition order, so `tools/list` ordering follows the order your methods appear in the file.

---

## Step 4 — Register the domain module in `__init__.py`

**If adding a method to an existing domain class** — nothing to do; its `SCHEMAS`/`HANDLERS` are already imported and `build()` picks the new method up automatically.

**If creating a new domain file** — add one import pair and one entry each to the `TOOLS`/`CMS_TOOLS` list and `_HANDLER_REGISTRY` in the appropriate `__init__.py`.

### For a new CDS domain (`mcp/cds/__init__.py`)

```python
from mcp.cds.widgets import HANDLERS as _WIDGETS_HANDLERS
from mcp.cds.widgets import SCHEMAS as _WIDGETS_SCHEMAS

TOOLS: list[dict] = (
    _POSTS_SCHEMAS
    + ...
    + _WIDGETS_SCHEMAS          # ← append
)

_HANDLER_REGISTRY: dict = {
    **_POSTS_HANDLERS,
    ...
    **_WIDGETS_HANDLERS,        # ← append
}
```

### For a new CMS domain (`mcp/cms/__init__.py`)

```python
from mcp.cms.widgets import HANDLERS as _WIDGETS_H
from mcp.cms.widgets import SCHEMAS as _WIDGETS_S

CMS_TOOLS: list[dict] = (
    _CAT_S + ... + _WIDGETS_S          # ← append
)

_HANDLER_REGISTRY: dict = {
    **_CAT_H, ..., **_WIDGETS_H,       # ← append
}

# CMS_TOOL_NAMES is rebuilt from _HANDLER_REGISTRY automatically — no edit needed.
```

---

## Step 5 — Verify

There is no test suite in this repo, so verification is import-time. Both
commands load Django settings the same way `manage.py` does.

```bash
# 1. Django sanity check — catches import errors in the changed modules
python manage.py check

# 2. Confirm tool count, that every tool has a handler, and CMS routing.
#    Run through manage.py shell so DJANGO_SETTINGS_MODULE is configured.
python manage.py shell -c "
from mcp.cds import TOOLS, _HANDLER_REGISTRY as CDS
from mcp.cms import CMS_TOOLS, CMS_TOOL_NAMES, _HANDLER_REGISTRY as CMS
all_ok = all(t['name'] in CDS for t in TOOLS) and all(t['name'] in CMS for t in CMS_TOOLS)
print('Tools:', len(TOOLS) + len(CMS_TOOLS), '| All handlers present:', all_ok, '| CMS routed:', len(CMS_TOOL_NAMES))
"
```

No migration, no server restart needed — the tool list is built at import time.

---

## Imports each domain file needs

```python
# CDS domain file
from mcp.clients.cds import cds_client
from mcp.tool_registry import PAGINATION_PROPERTIES, ToolModule, tool

# CMS read-only domain file (list/get/validate)
from mcp.clients.cms import cms_client
from mcp.tool_registry import PAGINATION_PROPERTIES, ToolModule, tool

# CMS write domain file (create/update/delete)
from mcp.clients.cms import cms_client  # noqa: F401 — kept as a test patch target
from mcp.tool_registry import PAGINATION_PROPERTIES, tool
from mcp.cms.helpers import CmsToolModule

# CMS domain that also needs CDS (e.g. cross-validation)
from mcp.clients.cds import cds_client
from mcp.clients.cms import cms_client
```

Tests patch the client at the module's import site (e.g. patch `mcp.cms.categories.cms_client`), which is why write modules keep the `cms_client` import even when handlers reach it through `self.client`.

---

## Error Handling Rules

1. **Never add try/except around client calls** (except the documented fallback pattern in `references/tool-patterns.md`). The clients handle retries, timeouts, and error normalisation. They return either a parsed JSON dict or `{"error_type": "...", "message": "...", "retryable": true/false}`.

2. **Always propagate client errors in dry-run branches.** The `CmsToolModule` helpers already do this; if you hand-write a dry-run branch:
   ```python
   current = self.client.get(credentials, path)
   if "error_type" in current:
       return current      # 404, auth error, timeout — surface it, don't crash
   ```

3. **For input validation errors**, return without calling the client:
   ```python
   return {"error": "invalid_input", "message": "widget_id must be a positive integer."}
   ```

4. **For create tools with special API constraints** (e.g. `create_post` requires contributors), validate before delegating to `create_resource` and return a `missing_required_field` error.

---

## References

- `references/tool-patterns.md` — full `@tool` method examples for each tier, inputSchema quick-reference, special patterns (publish gate, integer coercion, 500-idempotency, nested live-blog paths), and common mistakes
- `mcp/tool_registry.py` — `ToolModule`, `tool`, `PAGINATION_PROPERTIES`, shared `list_resource`/`get_resource`
- `mcp/cms/helpers.py` — `CmsToolModule`, `preview_*_op`, `DELETION_REQUIRES_CONFIRMATION`, `validate_live_blog_post_type`
- `mcp/clients/cds.py` — `cds_client.get` / `cds_client.is_not_found` and retry behaviour
- `mcp/clients/cms.py` — `cms_client.get/post/patch/delete` and error normalisation
