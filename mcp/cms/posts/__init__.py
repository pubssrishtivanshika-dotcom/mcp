"""CMS post tools package.

Split out of the former single ``posts.py`` for readability:
  - :mod:`.media_helpers`   — media id resolution, image-path normalization, slide serialization
  - :mod:`.payload_helpers` — payload coercion and upstream-error remapping
  - :mod:`.journey`         — per-type dashboard "Post Content" user journeys
  - :mod:`.tools`           — the ``CmsPostsTools`` module (list/get/create/update/delete)

The package re-exports ``SCHEMAS`` / ``HANDLERS`` so ``mcp.cms`` keeps importing
``from mcp.cms.posts import SCHEMAS, HANDLERS`` unchanged.
"""
from mcp.cms.posts.tools import HANDLERS, SCHEMAS, CmsPostsTools, cms_posts_tools

__all__ = ["SCHEMAS", "HANDLERS", "CmsPostsTools", "cms_posts_tools"]
