PAGINATION_PROPERTIES: dict = {
    "page":  {"type": "integer", "description": "Page number (default: 1, max: 1000)"},
    "limit": {"type": "integer", "description": "Items per page (default: 10, max: 50)"},
}


def tool(*, name: str, description: str, inputSchema: dict):
    """Mark a handler method as an MCP tool, attaching its schema."""
    def decorator(fn):
        fn._tool_schema = {"name": name, "description": description, "inputSchema": inputSchema}
        return fn
    return decorator


class ToolModule:
    """Base class for a tool module's handler class."""

    client = None  # set by subclasses to cds_client / cms_client

    def build(self) -> tuple[list[dict], dict]:
        """Derive (SCHEMAS, HANDLERS) from this instance's ``@tool``-decorated methods. """
        schemas: list[dict] = []
        handlers: dict = {}
        for attr_name, attr in type(self).__dict__.items():
            schema = getattr(attr, "_tool_schema", None)
            if schema is not None:
                schemas.append(schema)
                handlers[schema["name"]] = getattr(self, attr_name)
        return schemas, handlers

    def list_resource(self, credentials: dict, args: dict, *, path: str):
        """Paginated list one-liner shared by every mechanical list_* handler."""
        return self.client.get(credentials, path, {"page": args.get("page"), "limit": args.get("limit")})

    def get_resource(self, credentials: dict, args: dict, *, path_for, id_key: str = "id"):
        """Get-by-id one-liner shared by every mechanical get_* handler. """
        return self.client.get(credentials, path_for(args[id_key]))
