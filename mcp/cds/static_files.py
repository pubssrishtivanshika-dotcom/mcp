"""CDS static file tools — publisher-specific files served from S3."""
from mcp.clients.cds import cds_client
from mcp.tool_registry import ToolModule, tool

_path_for = "/static/{}/".format


class StaticFilesTools(ToolModule):
    client = cds_client

    @tool(
        name="fetch_static_file",
        description=(
            "Get a publisher-specific static file. "
            "ads.txt and robots.txt are always present. "
            "service-worker.js and the push notification HTML files (izooto.html, helper-iframe.html, permission-dialog.html) "
            "return 404 if push notifications are not enabled for this publisher."
        ),
        inputSchema={
            "type": "object",
            "required": ["filename"],
            "properties": {
                "filename": {
                    "type": "string",
                    "enum": [
                        "ads.txt",
                        "robots.txt",
                        "service-worker.js",
                        "izooto.html",
                        "helper-iframe.html",
                        "permission-dialog.html",
                    ],
                    "description": "Name of the static file to fetch",
                },
            },
        },
    )
    def fetch_static_file(self, credentials: dict, args: dict):
        return self.get_resource(credentials, args, path_for=_path_for, id_key="filename")


static_files_tools = StaticFilesTools()
SCHEMAS, HANDLERS = static_files_tools.build()
