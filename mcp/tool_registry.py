"""Decorator-based tool registry shared by the CDS and CMS tool packages.

A tool module defines one ``ToolModule`` subclass whose handler methods are each
annotated with ``@tool(...)`` carrying that tool's MCP schema. The module then
instantiates the class once and calls ``.build()`` on the instance to derive the
``SCHEMAS`` list and ``HANDLERS`` mapping the package ``__init__`` aggregates —
so the tool name, its schema and its handler all live together on one method
instead of being repeated across a separate ``SCHEMAS`` list and ``HANDLERS`` dict.

The shared paginated ``list_*`` / get-by-id ``get_*`` boilerplate lives here too
as ``ToolModule`` methods (using ``self.client``), and the pagination inputSchema
fragment is ``PAGINATION_PROPERTIES``.
"""

# Pagination inputSchema properties shared verbatim by paginated list_* tools.
# Spread into a schema's "properties" with ``**PAGINATION_PROPERTIES``.
PAGINATION_PROPERTIES: dict = {
    "page":  {"type": "integer", "description": "Page number (default: 1, max: 1000)"},
    "limit": {"type": "integer", "description": "Items per page (default: 10, max: 50)"},
}


def tool(*, name: str, description: str, inputSchema: dict):
    """Mark a handler method as an MCP tool, attaching its schema.

    ``ToolModule.build()`` collects every method carrying the resulting
    ``_tool_schema`` attribute. The wrapped function is returned unchanged, so the
    method stays directly callable as ``handler(credentials, args)``.
    """
    def decorator(fn):
        fn._tool_schema = {"name": name, "description": description, "inputSchema": inputSchema}
        return fn
    return decorator


class ToolModule:
    """Base class for a tool module's handler class.

    Subclasses set ``client`` to the cds/cms client singleton and decorate their
    handler methods with ``@tool(...)``. ``build()`` returns ``(SCHEMAS, HANDLERS)``
    in method-definition order.
    """

    client = None  # set by subclasses to cds_client / cms_client

    def build(self) -> tuple[list[dict], dict]:
        """Derive (SCHEMAS, HANDLERS) from this instance's ``@tool``-decorated methods.

        Iterates ``type(self).__dict__`` so tools come out in class-body definition
        order (preserved in CPython 3.7+); ``dir()`` is intentionally avoided as it
        sorts and would reorder ``tools/list``.
        """
        schemas: list[dict] = []
        handlers: dict = {}
        for attr_name, attr in type(self).__dict__.items():
            schema = getattr(attr, "_tool_schema", None)
            if schema is not None:
                schemas.append(schema)
                handlers[schema["name"]] = getattr(self, attr_name)
        return schemas, handlers

    # --- Shared read handlers (use self.client) ----------------------------
    def list_resource(self, credentials: dict, args: dict, *, path: str):
        """Paginated list one-liner shared by every mechanical list_* handler."""
        return self.client.get(credentials, path, {"page": args.get("page"), "limit": args.get("limit")})

    def get_resource(self, credentials: dict, args: dict, *, path_for, id_key: str = "id"):
        """Get-by-id one-liner shared by every mechanical get_* handler.

        ``path_for`` maps the identifier to its resource path (bases differ, e.g.
        ``/category/{}/`` vs ``/static/{}/``). ``id_key`` is the argument name
        carrying the identifier — "id" for CMS, "identifier"/"filename" for some CDS tools.
        """
        return self.client.get(credentials, path_for(args[id_key]))
