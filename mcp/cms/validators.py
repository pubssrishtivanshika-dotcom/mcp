"""Read-only pre-flight validation tools — no CMS writes."""
from mcp.clients.cds import cds_client
from mcp.clients.cms import cms_client
from mcp.tool_registry import ToolModule, tool


class ValidatorsTools(ToolModule):
    @tool(
        name="validate_media_asset",
        description=(
            "Validation check — no changes made. "
            "Checks whether a media asset with the given ID exists in the CMS library. "
            "Returns {valid: true, id, filename, path} if found, {valid: false, reason} if not."
        ),
        inputSchema={
            "type": "object",
            "required": ["id"],
            "properties": {"id": {"type": "integer", "description": "Media asset ID to validate"}},
        },
    )
    def validate_media_asset(self, credentials: dict, args: dict):
        media_id = args["id"]
        result   = cms_client.get(credentials, f"/media-library/{media_id}/")
        if "error_type" in result:
            return {"valid": False, "reason": f"Media ID {media_id} not found."}
        return {"valid": True, "id": media_id, "filename": result.get("filename"), "path": result.get("path")}

    @tool(
        name="validate_category",
        description=(
            "Validation check — no changes made. "
            "Checks whether a category with the given ID exists in the CMS. "
            "Returns {valid: true, id, name} if found, {valid: false, reason} if not."
        ),
        inputSchema={
            "type": "object",
            "required": ["id"],
            "properties": {"id": {"type": "integer", "description": "Category ID to validate"}},
        },
    )
    def validate_category(self, credentials: dict, args: dict):
        category_id = args["id"]
        result      = cms_client.get(credentials, f"/category/{category_id}/")
        if "error_type" in result:
            return {"valid": False, "reason": f"Category ID {category_id} not found."}
        return {"valid": True, "id": category_id, "name": result.get("name")}

    @tool(
        name="validate_author",
        description=(
            "Validation check — no changes made. "
            "Checks whether a contributor/author with the given ID exists via the CDS. "
            "Returns {valid: true, id, name} if found, {valid: false, reason} if not."
        ),
        inputSchema={
            "type": "object",
            "required": ["id"],
            "properties": {"id": {"type": "integer", "description": "Author/contributor ID to validate"}},
        },
    )
    def validate_author(self, credentials: dict, args: dict):
        author_id = args["id"]
        result    = cds_client.get(credentials, f"/author/{author_id}/")
        if isinstance(result, dict) and "error_type" in result:
            if cds_client.is_not_found(result):
                return {"valid": False, "reason": f"Author ID {author_id} not found."}
            return result  # surface real errors (auth/upstream) rather than masking as not-found
        data = result.get("data", result)
        return {"valid": True, "id": author_id, "name": data.get("name") if isinstance(data, dict) else result.get("name")}

    @tool(
        name="validate_post_slug",
        description=(
            "Validation check — no changes made. "
            "Checks whether a post slug is available (not yet taken) among published posts. "
            "Returns {valid: true, slug, available: true} if the slug is free, "
            "{valid: false, available: false, reason} if it is already taken. "
            "Note: only published content is checked, so a slug reserved by an unpublished "
            "draft or scheduled post may still report as available."
        ),
        inputSchema={
            "type": "object",
            "required": ["slug"],
            "properties": {"slug": {"type": "string", "minLength": 1, "description": "URL slug to check for availability"}},
        },
    )
    def validate_post_slug(self, credentials: dict, args: dict):
        slug = args["slug"]
        # The CMS GET /post/{id}/ path accepts an integer ID only, so it cannot look up
        # a slug. The CDS post-details endpoint accepts an ID *or* slug as its identifier,
        # so use it here. Note: CDS only indexes published content, so a slug held by an
        # unpublished draft/scheduled post will still report as available.
        result = cds_client.get(credentials, f"/post/{slug}/")
        if isinstance(result, dict) and "error_type" in result:
            if cds_client.is_not_found(result):
                return {"valid": True, "slug": slug, "available": True}
            return result  # surface real errors (auth/upstream) rather than masking as available
        data = result.get("data", result) if isinstance(result, dict) else {}
        post_id = data.get("id") if isinstance(data, dict) else None
        return {"valid": False, "slug": slug, "available": False,
                "reason": f"Slug '{slug}' is already taken by post ID {post_id}."}


validators_tools = ValidatorsTools()
SCHEMAS, HANDLERS = validators_tools.build()
