# Tool Patterns Reference

Complete `@tool`-decorated method examples for every tier, matching the actual codebase style
(`ToolModule` / `CmsToolModule` subclasses, `cds_client` / `cms_client` singletons).
Copy–paste and substitute your resource name and endpoint path.

---

## inputSchema Quick-Reference

| Field type | JSON Schema |
|---|---|
| Integer ID | `{"type": "integer", "description": "Resource ID"}` |
| String ID or slug | `{"type": "string", "minLength": 1, "description": "Resource ID or slug"}` |
| Boolean flag | `{"type": "boolean", "description": "..."}` |
| HTML content | `{"type": "string", "description": "HTML body content"}` |
| Hex colour | `{"type": "string", "description": "Brand colour in hex (e.g. #EF4444)"}` |
| ISO 8601 timestamp | `{"type": "string", "description": "... (ISO 8601)"}` |
| Comma-separated IDs | `{"type": "string", "description": "Comma-separated IDs (e.g. '1,2,3')"}` |
| Pagination (page + limit) | `**PAGINATION_PROPERTIES` — spread the shared fragment, don't retype |
| dry_run | `{"type": "boolean", "description": "true = preview only, no changes (default); false = execute"}` |
| confirm_delete | `{"type": "boolean", "description": "Must be true — together with dry_run=false — to permanently delete"}` |

`PAGINATION_PROPERTIES` lives in `mcp.tool_registry` and expands to:
```python
{"page":  {"type": "integer", "description": "Page number (default: 1, max: 1000)"},
 "limit": {"type": "integer", "description": "Items per page (default: 10, max: 50)"}}
```

---

## Module skeleton

Every domain file is one `ToolModule` (CDS / CMS-read) or `CmsToolModule` (CMS-write) subclass,
instantiated once, with `.build()` deriving `SCHEMAS`/`HANDLERS`:

```python
# mcp/cds/widgets.py
from mcp.clients.cds import cds_client
from mcp.tool_registry import PAGINATION_PROPERTIES, ToolModule, tool


class WidgetsTools(ToolModule):
    client = cds_client

    # @tool-decorated methods go here …


widgets_tools = WidgetsTools()
SCHEMAS, HANDLERS = widgets_tools.build()   # ← never hand-write these two
```

---

## Tier 0 — CDS Read: list with filters

```python
    @tool(
        name="list_widgets",
        description=(
            "List all published widgets with pagination and optional status filter. "
            "If the user needs unpublished widgets, use list_editorial_widgets instead."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                **PAGINATION_PROPERTIES,
                "status__eq": {"type": "string", "description": "Filter by status: active or inactive"},
                "sort_by":    {"type": "string", "description": "Sort field e.g. created_at"},
                "sort_order": {"type": "string", "description": "asc or desc"},
            },
        },
    )
    def list_widgets(self, credentials: dict, args: dict):
        # self.list_resource only forwards page+limit — when there are extra filters,
        # call the client directly:
        return self.client.get(credentials, "/widgets/", {
            "page":       args.get("page"),
            "limit":      args.get("limit"),
            "status__eq": args.get("status__eq"),
            "sort_by":    args.get("sort_by"),
            "sort_order": args.get("sort_order"),
        })
```

For a plain paginated list (no extra filters) use the shared one-liner instead:

```python
    def list_widgets(self, credentials: dict, args: dict):
        return self.list_resource(credentials, args, path="/widgets/")
```

---

## Tier 0 — CDS Read: get by ID/slug with input validation

```python
    @tool(
        name="get_widget",
        description=(
            "Get a single published widget by ID or slug. "
            "Use list_widgets to discover valid identifiers."
        ),
        inputSchema={
            "type": "object",
            "required": ["identifier"],
            "properties": {
                "identifier": {"type": "string", "minLength": 1, "description": "Widget ID or slug"},
            },
        },
    )
    def get_widget(self, credentials: dict, args: dict):
        identifier = str(args.get("identifier", "")).strip()
        if not identifier:
            return {"error": "invalid_input",
                    "message": "identifier is required. Use list_widgets to discover valid IDs."}
        return self.client.get(credentials, f"/widget/{identifier}/")
```

Plain get-by-id (no validation) uses the shared one-liner with a `path_for` callable:

```python
_path_for = "/widget/{}/".format   # module level

    def get_widget(self, credentials: dict, args: dict):
        return self.get_resource(credentials, args, path_for=_path_for)
        # id_key defaults to "id"; pass id_key="identifier"/"filename" where it differs
```

---

## Tier 0 — CDS Read: strict numeric ID + not-found shaping

Use when the API only accepts integer IDs and you want a friendly 404.

```python
    def fetch_author(self, credentials: dict, args: dict):
        identifier = str(args.get("identifier", "")).strip()
        if not identifier:
            return {"error": "invalid_input", "message": "identifier is required."}
        if not identifier.isdigit():
            return {"error": "invalid_input",
                    "message": f"Author identifier must be a numeric ID, got {identifier!r}. "
                               "Use fetch_authors to discover valid author IDs."}
        result = cds_client.get(credentials, f"/author/{identifier}/")
        if isinstance(result, dict) and cds_client.is_not_found(result):
            return {"error": "not_found",
                    "message": f"Author with ID {identifier} was not found."}
        return result
```

---

## Tier 0 — CDS Read: fallback on endpoint missing

Use when the primary endpoint is not available for all publishers. This is the **one**
sanctioned try/except around a client call.

```python
    def fetch_publisher_profile(self, credentials: dict, args: dict):
        try:
            return cds_client.get(credentials, "/publisher-data/")
        except Exception as exc:
            err_str     = str(exc).lower()
            http_status = getattr(getattr(exc, "response", None), "status_code", None)
            is_missing  = (
                http_status in (400, 404)
                or "unknown endpoint" in err_str
                or "not found"        in err_str
            )
            if is_missing:
                logger.warning("fetch_publisher_profile: primary endpoint unavailable — falling back to /footer/")
                return cds_client.get(credentials, "/footer/")
            raise
```

---

## Tier 1 — CMS Read: list + get (no dry_run)

CMS read-only tools subclass **`ToolModule`** (not `CmsToolModule`) and set `client = cms_client`.

```python
# mcp/cms/widgets.py
from mcp.clients.cms import cms_client
from mcp.tool_registry import PAGINATION_PROPERTIES, ToolModule, tool

_path_for = "/widget/{}/".format


class CmsWidgetsTools(ToolModule):
    client = cms_client

    @tool(
        name="list_editorial_widgets",
        description=(
            "List all CMS widgets with pagination. Returns every widget including unpublished ones. "
            "If the user only needs published widgets, prefer the CDS list_widgets tool. "
            "Returns results directly — no confirmation step needed."
        ),
        inputSchema={"type": "object", "properties": {**PAGINATION_PROPERTIES}},
    )
    def list_editorial_widgets(self, credentials: dict, args: dict):
        return self.list_resource(credentials, args, path="/widget/")

    @tool(
        name="get_editorial_widget",
        description=(
            "Retrieve a single CMS widget by ID. Returns full management details including unpublished fields. "
            "If the user only needs basic published data, prefer the CDS get_widget tool. "
            "Returns results directly — no confirmation step needed."
        ),
        inputSchema={
            "type": "object",
            "required": ["id"],
            "properties": {"id": {"type": "integer", "description": "Widget ID"}},
        },
    )
    def get_editorial_widget(self, credentials: dict, args: dict):
        return self.get_resource(credentials, args, path_for=_path_for)


cms_widgets_tools = CmsWidgetsTools()
SCHEMAS, HANDLERS = cms_widgets_tools.build()
```

---

## Tier 2 — CMS Create (dry_run preview → POST)

CMS write tools subclass **`CmsToolModule`** (which sets `client = cms_client`) and delegate to
`self.create_resource`. The base owns the whole dry_run flow.

```python
from mcp.clients.cms import cms_client  # noqa: F401 — kept as a test patch target
from mcp.tool_registry import tool
from mcp.cms.helpers import CmsToolModule


class CmsWidgetsTools(CmsToolModule):

    @tool(
        name="create_widget",
        description=(
            "Create a new widget in the CMS. "
            "BEFORE calling: confirm all details with the user — at minimum name and english_name. "
            "Workflow: dry_run=true (default) shows a full preview — no changes made. "
            "Once the user confirms, call again with dry_run=false to create. "
            "Immutable after creation: english_name, slug."
        ),
        inputSchema={
            "type": "object",
            "required": ["name", "english_name"],
            "properties": {
                "name":         {"type": "string",  "minLength": 1, "description": "Widget name"},
                "english_name": {"type": "string",  "minLength": 1, "description": "English name for slug generation. Immutable after creation."},
                "slug":         {"type": "string",  "description": "Custom slug (auto-generated if omitted). Immutable after creation."},
                "content":      {"type": "string",  "description": "Widget HTML content"},
                "priority":     {"type": "integer", "description": "Sort priority (1–1000)"},
                "dry_run":      {"type": "boolean", "description": "true = preview only, no changes (default); false = create for real"},
            },
        },
    )
    def create_widget(self, credentials: dict, args: dict):
        return self.create_resource(credentials, args, resource="Widget", path="/widget/")
```

---

## Tier 3 — CMS Update (dry_run diff → PATCH)

```python
_path_for = "/widget/{}/".format

    @tool(
        name="update_widget",
        description=(
            "Update an existing widget. "
            "BEFORE calling: confirm the widget ID and all fields to change with the user. "
            "Workflow: dry_run=true (default) fetches current state and shows a field-by-field diff — no changes made. "
            "Show the diff to the user. Once they confirm, call again with dry_run=false to apply. "
            "Immutable fields that cannot be changed: english_name, slug."
        ),
        inputSchema={
            "type": "object",
            "required": ["id"],
            "properties": {
                "id":       {"type": "integer", "description": "Widget ID"},
                "name":     {"type": "string",  "description": "New widget name"},
                "content":  {"type": "string",  "description": "New HTML content"},
                "priority": {"type": "integer", "description": "New sort priority"},
                "dry_run":  {"type": "boolean", "description": "true = show diff only, no changes (default); false = apply update"},
            },
        },
    )
    def update_widget(self, credentials: dict, args: dict):
        return self.update_resource(credentials, args, resource="Widget", path_for=_path_for)
```

---

## Tier 3 — CMS Delete (dry_run preview → DELETE + double confirm)

```python
    @tool(
        name="delete_widget",
        description=(
            "Permanently delete a widget. This action CANNOT be undone. "
            "Posts referencing this widget will lose their widget association. "
            "BEFORE calling: confirm the widget ID with the user. "
            "Workflow: dry_run=true (default) fetches and shows full widget details — no deletion. "
            "Show the preview to the user. Once they explicitly confirm, call again with "
            "dry_run=false AND confirm_delete=true."
        ),
        inputSchema={
            "type": "object",
            "required": ["id"],
            "properties": {
                "id":             {"type": "integer", "description": "Widget ID"},
                "dry_run":        {"type": "boolean", "description": "true = preview only (default); false = delete (also requires confirm_delete=true)"},
                "confirm_delete": {"type": "boolean", "description": "Must be explicitly set to true — together with dry_run=false — to execute the deletion"},
            },
        },
    )
    def delete_widget(self, credentials: dict, args: dict):
        return self.delete_resource(
            credentials, args, resource="Widget", path_for=_path_for,
            warning="Posts referencing this widget will lose their widget association.",
        )
```

The `CmsToolModule` base methods (`create_resource` / `update_resource` / `delete_resource` in
`mcp/cms/helpers.py`) handle the preview formatting, fetch-current-state-for-diff, client-error
propagation, and the `dry_run=false AND confirm_delete=true` gate. Only hand-write a body for the
non-standard flows below.

---

## Validation tool (read-only pre-flight; subclass ToolModule)

```python
    @tool(
        name="validate_widget",
        description=(
            "Validation check — no changes made. "
            "Checks whether a widget with the given ID exists in the CMS. "
            "Returns {valid: true, id, name} if found, {valid: false, reason} if not."
        ),
        inputSchema={
            "type": "object",
            "required": ["id"],
            "properties": {"id": {"type": "integer", "description": "Widget ID to validate"}},
        },
    )
    def validate_widget(self, credentials: dict, args: dict):
        result = cms_client.get(credentials, f"/widget/{args['id']}/")
        if "error_type" in result:
            return {"valid": False, "reason": f"Widget ID {args['id']} not found."}
        return {"valid": True, "id": args["id"], "name": result.get("name")}
```

---

## Special pattern — nested resource paths (live_blog style)

When a resource hangs off a parent (e.g. `/post/{post_id}/live-blog-update/{id}/`), the shared
`create_resource`/`update_resource`/`delete_resource` helpers don't fit (they assume a single id).
Hand-write the body, calling `cms_client` directly and composing the preview formatters:

```python
from mcp.cms.helpers import (
    DELETION_REQUIRES_CONFIRMATION, preview_delete_op, preview_update_op,
)

    def delete_liveblog_update(self, credentials: dict, args: dict):
        dry_run        = args.get("dry_run", True)
        confirm_delete = args.get("confirm_delete", False)
        post_id, update_id = args["post_id"], args["id"]
        path = f"/post/{post_id}/live-blog-update/{update_id}/"
        if dry_run:
            item = cms_client.get(credentials, path)
            if "error_type" in item:
                return item
            return {"dry_run": True, "preview": preview_delete_op("LiveBlog update", update_id, item)}
        if not confirm_delete:
            return DELETION_REQUIRES_CONFIRMATION
        return cms_client.delete(credentials, path)
```

---

## Special pattern — publish gate (update_post style)

When setting `status=Published` requires an extra explicit confirmation, hand-write the update:

```python
    def update_widget(self, credentials: dict, args: dict):
        dry_run         = args.get("dry_run", True)
        confirm_publish = args.get("confirm_publish", False)
        widget_id       = args["id"]
        changes         = {k: v for k, v in args.items() if k not in ("id", "dry_run", "confirm_publish")}

        # Draft is always safe — apply immediately without preview
        if changes.get("status") == "Draft":
            return cms_client.patch(credentials, f"/widget/{widget_id}/", changes)

        if dry_run:
            current = cms_client.get(credentials, f"/widget/{widget_id}/")
            if "error_type" in current:
                return current
            return {"dry_run": True, "preview": preview_update_op("Widget", widget_id, current, changes)}

        if changes.get("status") == "Published" and not confirm_publish:
            return {"error_type": "confirmation_required",
                    "message": "Publishing requires confirm_publish=true. "
                               "Call again with dry_run=false AND confirm_publish=true.",
                    "retryable": False}
        return cms_client.patch(credentials, f"/widget/{widget_id}/", changes)
```

Add `"confirm_publish"` to the inputSchema too:
```python
"confirm_publish": {"type": "boolean", "description": "Must be true when setting status=Published with dry_run=false."},
```

---

## Special pattern — integer field coercion (create_post style)

When AI clients may send integer fields as strings (e.g. `"156228"` instead of `156228`),
hand-write the create rather than using `create_resource`:

```python
    def create_widget(self, credentials: dict, args: dict):
        dry_run = args.get("dry_run", True)
        payload = {k: v for k, v in args.items() if k != "dry_run" and v is not None and v != ""}

        for field in ("primary_category", "banner_url"):
            if field in payload:
                try:
                    payload[field] = int(payload[field])
                except (ValueError, TypeError):
                    pass

        if dry_run:
            return {"dry_run": True, "preview": preview_create_op("Widget", payload)}
        return cms_client.post(credentials, "/widget/", payload)
```

---

## Special pattern — upstream 500 idempotency check (create_component_schema style)

When the API sometimes 500s after actually committing the write, check before retrying:

```python
    def create_widget(self, credentials: dict, args: dict):
        dry_run = args.get("dry_run", True)
        payload = {k: v for k, v in args.items() if k != "dry_run"}
        if dry_run:
            return {"dry_run": True, "preview": preview_create_op("Widget", payload)}
        result = cms_client.post(credentials, "/widget/", payload)
        if isinstance(result, dict) and result.get("error_type") == "upstream_error":
            listing = cms_client.get(credentials, "/widget/", {"limit": 50})
            items   = (listing.get("results") or listing.get("data") or []) if isinstance(listing, dict) and not listing.get("error_type") else []
            for item in items:
                if isinstance(item, dict) and item.get("name") == payload.get("name"):
                    return item
            result = cms_client.post(credentials, "/widget/", payload)
        return result
```

---

## Common Mistakes

| Mistake | Fix |
|---|---|
| Hand-writing a `SCHEMAS` list or `HANDLERS` dict | Don't — decorate methods with `@tool(...)` and call `SCHEMAS, HANDLERS = tools.build()` |
| Subclassing `CmsToolModule` for a read-only CMS tool | Read-only CMS (list/get/validate) subclasses `ToolModule` with `client = cms_client`; only create/update/delete use `CmsToolModule` |
| Calling a non-existent `cms_get`/`cds_get` free function | Those were removed — use `cms_client.get(...)` / `cds_client.get(...)` (or `self.client.get`) |
| Forgetting `if "error_type" in current: return current` in a hand-written dry-run branch | Always propagate client errors before passing `current` to `preview_update_op` (the `CmsToolModule` helpers already do this) |
| New CMS tool with a non-`cms_`/`validate_` name routes to CDS | `CMS_TOOL_NAMES` is derived from `_HANDLER_REGISTRY` — as long as the tool's module is imported into `mcp/cms/__init__.py`, routing is correct regardless of name |
| Creating a new domain file but forgetting to import it | Always add the `SCHEMAS`/`HANDLERS` import + registry entries in the corresponding `__init__.py` |
| Adding `required: ["dry_run"]` to a CMS write tool | `dry_run` is always optional with a `True` default — never required |
| Retyping `page`/`limit` in a list schema | Spread `**PAGINATION_PROPERTIES` from `mcp.tool_registry` |
| Stripping `None` values in update payload | For PATCH, only strip `"id"` and `"dry_run"` (the `update_resource` helper does this) — let the caller decide which fields to update |
