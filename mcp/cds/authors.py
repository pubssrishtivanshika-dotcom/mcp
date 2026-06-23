import logging

from mcp.clients.cds import cds_client
from mcp.tool_registry import PAGINATION_PROPERTIES, ToolModule, tool

logger = logging.getLogger(__name__)


class AuthorsTools(ToolModule):
    client = cds_client

    @tool(
        name="fetch_authors",
        description="List all authors/contributors for this publication with pagination.",
        inputSchema={
            "type": "object",
            "properties": {
                **PAGINATION_PROPERTIES,
            },
        },
    )
    def fetch_authors(self, credentials: dict, args: dict):
        return self.list_resource(credentials, args, path="/authors/")

    @tool(
        name="fetch_author",
        description=(
            "Get a single author by their numeric ID. "
            "identifier must be a numeric author ID. "
            "To find posts by a specific author, use fetch_published_posts with the contributors.id__eq filter. "
            "Do not guess IDs or pass non-numeric values."
        ),
        inputSchema={
            "type": "object",
            "required": ["identifier"],
            "properties": {
                "identifier": {"type": "string", "minLength": 1, "description": "Numeric author ID (e.g. \"42\")."},
            },
        },
    )
    def fetch_author(self, credentials: dict, args: dict):
        identifier = str(args.get("identifier", "")).strip()
        if not identifier:
            return {"error": "invalid_input", "message": "identifier is required. Use fetch_authors to find valid numeric author IDs."}
        if not identifier.isdigit():
            logger.warning("fetch_author: non-numeric identifier=%r", identifier)
            return {
                "error": "invalid_input",
                "message": (
                    f"Author identifier must be a numeric ID, got {identifier!r}. "
                    "Use fetch_authors to discover valid author IDs."
                ),
            }
        result = cds_client.get(credentials, f"/author/{identifier}/")
        if isinstance(result, dict) and cds_client.is_not_found(result):
            return {
                "error": "not_found",
                "message": (
                    f"Author with ID {identifier} was not found. "
                    "Use fetch_authors to discover valid author IDs."
                ),
            }
        return result


authors_tools = AuthorsTools()
SCHEMAS, HANDLERS = authors_tools.build()
