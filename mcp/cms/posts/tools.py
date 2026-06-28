"""CMS post write tools — the ``CmsPostsTools`` module (list/get/create/update/delete).

This is a thin wiring layer: tool descriptions and input schemas live in :mod:`.schemas`,
the heavy create/update flows live in :mod:`.operations`, and the shared helpers live in
:mod:`.media_helpers` / :mod:`.payload_helpers` / :mod:`.journey`.
"""
import logging

from mcp.tool_registry import tool

from mcp.cms.helpers import CmsToolModule

from mcp.cms.posts import operations, schemas

logger = logging.getLogger(__name__)

_path_for = "/post/{}/".format


class CmsPostsTools(CmsToolModule):
    @tool(
        name="list_editorial_posts",
        description=schemas.LIST_DESCRIPTION,
        inputSchema=schemas.LIST_INPUT_SCHEMA,
    )
    def list_editorial_posts(self, credentials: dict, args: dict):
        return self.list_resource(credentials, args, path="/post/")

    @tool(
        name="get_editorial_post",
        description=schemas.GET_DESCRIPTION,
        inputSchema=schemas.GET_INPUT_SCHEMA,
    )
    def get_editorial_post(self, credentials: dict, args: dict):
        return self.get_resource(credentials, args, path_for=_path_for)

    @tool(
        name="create_post",
        description=schemas.CREATE_DESCRIPTION,
        inputSchema=schemas.CREATE_INPUT_SCHEMA,
    )
    def create_post(self, credentials: dict, args: dict):
        return operations.create_post(credentials, args)

    @tool(
        name="update_post",
        description=schemas.UPDATE_DESCRIPTION,
        inputSchema=schemas.UPDATE_INPUT_SCHEMA,
    )
    def update_post(self, credentials: dict, args: dict):
        return operations.update_post(credentials, args)

    @tool(
        name="delete_post",
        description=schemas.DELETE_DESCRIPTION,
        inputSchema=schemas.DELETE_INPUT_SCHEMA,
    )
    def delete_post(self, credentials: dict, args: dict):
        return self.delete_resource(
            credentials, args, resource="Post", path_for=_path_for,
            warning="This post and ALL its associated data will be permanently removed.",
        )


cms_posts_tools = CmsPostsTools()
SCHEMAS, HANDLERS = cms_posts_tools.build()
