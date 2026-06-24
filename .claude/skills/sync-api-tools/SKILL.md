---
name: sync-api-tools
description: >
  Use this skill when the user asks to "check for new APIs", "sync tools with
  docs", "find missing tools", "scaffold tools from the docs", "see if any
  Publive API is missing a tool", or wants to compare the publive-docs API
  reference against the tools implemented in this MCP server and create any
  that are missing. Manual/on-demand — run it whenever you want to check, it
  is not scheduled. For updating/patching *existing* tools that have drifted
  from the docs, use [[diff-api-tools]] instead.
version: 1.0.0
---

# Sync MCP Tools with the Publive Docs API Reference

Diffs the documented Publive APIs (via the `publive-docs` MCP server) against
the tools actually implemented in `mcp/cds/` and `mcp/cms/`, and
scaffolds any genuinely missing ones using the [[add-tool]] skill's patterns.

This is a **manual** workflow — run it on demand, it does not run on a schedule.

---

## Step 1 — Inventory the documented endpoints

Use the `publive-docs` MCP tools (`search_publive_docs` /
`query_docs_filesystem_publive_docs`) to list every endpoint under
`/api-reference`:

```
tree /api-reference -L 2
```

Read each leaf `.mdx` (skip `README.mdx` overview pages) to get the
method + path + description, e.g.:

```
head -25 /api-reference/content-management/<domain>/*.mdx
```

Build a flat list: `(domain, method, path, doc-name)`. Ignore everything under
`/api-reference/deprecated/` — those are explicitly deprecated, not gaps.

## Step 2 — Inventory the implemented tools

Read the aggregated tool lists directly — don't rely on grepping for `"name"`
strings:

```python
from mcp.cds import TOOLS as CDS_TOOLS
from mcp.cms import CMS_TOOLS
```

or read `mcp/cds/__init__.py` / `mcp/cms/__init__.py` and the
individual domain files' `SCHEMAS` lists.

## Step 3 — Match documented endpoints to tools

For each documented endpoint, decide whether an existing tool already covers
it. Use the naming conventions from [[add-tool]] (`fetch_*` / `resolve_*` for
CDS reads, `list_editorial_*` / `get_editorial_*` / `create_*` / `update_*` /
`delete_*` / `validate_*` for CMS) — a doc page like
`reader/login.mdx` maps conceptually to a tool like `login_reader`, even if
the exact name differs slightly. Read the handler body to confirm it calls the
matching path before concluding "covered".

### Respect intentional exclusions

Some documented endpoints are **deliberately not implemented**. The convention
in this repo is a one-line note in the relevant package `__init__.py` explaining
why, e.g. in `mcp/cms/__init__.py`:

```python
# Intentionally-excluded CMS endpoints (no tool by design — do not re-scaffold):
#   submit_form — removed: required a browser reCAPTCHA token, unusable in MCP context.
```

Before scaffolding anything, check whether such a note already documents an
exclusion — grep for `"removed:"` / `"unusable in MCP"` / `"do not re-scaffold"`
across `mcp/cds/` and `mcp/cms/`. Treat those as resolved, not gaps. Common reasons an endpoint
is legitimately excluded from an MCP context:

- Requires a browser-only flow (reCAPTCHA widget tokens, OAuth redirect dance)
- Returns/sets opaque session tokens with no further use inside an MCP tool
- Is a pure client-side no-op (e.g. `reader/logout/` makes no backend call)

When you hit one of these during the diff, use your judgment — flag it in the
report as "intentionally excluded — <reason>" rather than scaffolding a tool
that can't actually work, and ask the user before creating anything that looks
borderline (e.g. `reader/login/` *does* return a usable token even though it
also supports an OAuth flow the MCP can't drive).

## Step 4 — Present the gap list and let the user choose

**Do not scaffold anything yet.** First show the user every documented
endpoint that is genuinely missing (no tool, no documented exclusion) as a
numbered list — name, method+path, one-line description — and ask them which
ones (if any) they want tools created for. Use `AskUserQuestion` with
`multiSelect: true` when there are a handful of candidates (it caps at 4
options, so for longer lists present the full numbered list as plain text
first and ask them to reply with the numbers/names they want).

Also surface, in the same message, anything from the "needs a decision" or
"intentionally excluded" buckets that's borderline — the user may want to
override your judgment on those too.

Only proceed to scaffolding for the endpoints the user explicitly selects. If
they pick none, stop here and just leave the report.

## Step 5 — Scaffold the selected tools

For each endpoint the user selected, follow [[add-tool]] step by step:

1. Pick the right domain file (existing domain if it fits, new `mcp/cms/<domain>.py` otherwise — with its own `ToolModule`/`CmsToolModule` subclass)
2. Add an `@tool(...)`-decorated handler **method** to that class — the decorator carries the name, description, and inputSchema (there is no separate `SCHEMAS` list to edit)
3. Write the method body, matching the correct tier (CDS read / CMS list-get / create / update / delete / validate)
4. `SCHEMAS, HANDLERS = <module>.build()` at the bottom picks the new method up automatically — no `HANDLERS` dict to edit
5. Wire a new domain module into `__init__.py` (import its `SCHEMAS`/`HANDLERS`, append to the `TOOLS`/`CMS_TOOLS` list and `_HANDLER_REGISTRY`) if needed

Don't guess at request/response shapes — read the full `.mdx` doc page for
each endpoint (`cat /api-reference/.../<endpoint>.mdx`) to get the exact
parameters, required fields, and response examples before writing the schema.

## Step 6 — Verify and report

```bash
python manage.py check
python manage.py shell -c "
from mcp.cds import TOOLS, _HANDLER_REGISTRY as CDS
from mcp.cms import CMS_TOOLS, _HANDLER_REGISTRY as CMS
all_ok = all(t['name'] in CDS for t in TOOLS) and all(t['name'] in CMS for t in CMS_TOOLS)
print('Tools:', len(TOOLS) + len(CMS_TOOLS), '| All handlers present:', all_ok)
"
```

End with a short report:
- **Added**: tool names + doc pages they implement (only what the user selected in Step 4)
- **Skipped by user**: gap-list endpoints they chose not to create tools for
- **Already covered**: doc pages that map to existing tools (name the tool)
- **Intentionally excluded**: doc pages with no tool and why
- **Needs a decision**: anything ambiguous the user didn't address — don't scaffold these

If nothing is missing, just say so — no need to ask anything or touch any files.

---

## References

- [[add-tool]] — the canonical guide for writing the schema/handler/registration
- `mcp/cms/__init__.py` — example of the "intentionally excluded" note convention (see the `do not re-scaffold` comment)

<!-- trigger it any time with something like "check for new APIs" or "sync tools with docs". -->