"""CMS reader account tools — registration and password reset.

reader/logout is intentionally not implemented: per the docs it makes no backend call and
performs no token invalidation (token cleanup is fully client-side) — there's nothing for
an MCP tool to do.
"""
from mcp.clients.cms import cms_client
from mcp.tool_registry import ToolModule, tool


class ReaderTools(ToolModule):
    client = cms_client

    @tool(
        name="register_reader",
        description=(
            "Create a new reader account and trigger a verification email."
        ),
        inputSchema={
            "type": "object",
            "required": ["email", "password"],
            "properties": {
                "email":    {"type": "string", "minLength": 1, "description": "Reader's email address (normalized to lowercase before forwarding)"},
                "password": {"type": "string", "minLength": 1, "description": "Reader's password"},
                "name":     {"type": "string", "description": "Reader's display name (optional)"},
                "picture":  {"type": "string", "description": "URL of the reader's profile picture (optional)"},
            },
        },
    )
    def register_reader(self, credentials: dict, args: dict):
        return cms_client.post(credentials, "/reader/register/", {
            "email":    args["email"].lower(),
            "password": args["password"],
            "name":     args.get("name", ""),
            "picture":  args.get("picture", ""),
        })

    @tool(
        name="forgot_password_reader",
        description=(
            "Trigger a password-reset email for a reader. The email contains a one-time token "
            "to pass to reset_password_reader."
        ),
        inputSchema={
            "type": "object",
            "required": ["email"],
            "properties": {
                "email": {"type": "string", "minLength": 1, "description": "Reader's email address (normalized to lowercase before forwarding)"},
            },
        },
    )
    def forgot_password_reader(self, credentials: dict, args: dict):
        return cms_client.post(credentials, "/reader/forgot-password/", {"email": args["email"].lower()})

    @tool(
        name="reset_password_reader",
        description=(
            "Set a new password for a reader using the one-time reset token sent by "
            "forgot_password_reader. new_password and confirm_password must match — the "
            "request is rejected with an error if they don't."
        ),
        inputSchema={
            "type": "object",
            "required": ["email", "token", "new_password", "confirm_password"],
            "properties": {
                "email":            {"type": "string", "minLength": 1, "description": "Reader's email address (normalized to lowercase before forwarding)"},
                "token":            {"type": "string", "minLength": 1, "description": "One-time reset token from the password reset email"},
                "new_password":     {"type": "string", "minLength": 1, "description": "The reader's new password"},
                "confirm_password": {"type": "string", "minLength": 1, "description": "Must match new_password"},
            },
        },
    )
    def reset_password_reader(self, credentials: dict, args: dict):
        return cms_client.patch(credentials, "/reader/reset-password/", {
            "email":            args["email"].lower(),
            "token":            args["token"],
            "new_password":     args["new_password"],
            "confirm_password": args["confirm_password"],
        })

reader_tools = ReaderTools()
SCHEMAS, HANDLERS = reader_tools.build()
