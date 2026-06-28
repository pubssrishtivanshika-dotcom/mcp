"""Handler logic for the create_post / update_post tools.

These are the two heavy, branchy flows (the tiered safety model, the per-type dashboard
journeys, the create-retry fallback). They're plain functions taking ``(credentials, args)``;
the thin :class:`~mcp.cms.posts.tools.CmsPostsTools` methods delegate to them. The list / get /
delete tools stay in :mod:`.tools` since they're one-liners over the CmsToolModule base.
"""
from mcp.clients.cms import cms_client
from mcp.cms import helpers

from mcp.cms.posts.media_helpers import (
    _build_gallery_content,
    _build_web_story_content,
    _resolve_banner_url,
)
from mcp.cms.posts.payload_helpers import (
    _coerce_post_int_fields,
    _find_recent_post_by_english_title,
    _is_draft_status,
    _no_data_type_hint,
    _remap_post_type_error,
    _strip_list_brackets,
)
from mcp.cms.posts.journey import _build_video_embed_from_url, _check_post_journey


def create_post(credentials: dict, args: dict):
    dry_run = args.get("dry_run", True)
    payload = {k: v for k, v in args.items() if k != "dry_run" and v is not None and v != ""}

    if not payload.get("contributors"):
        return {
            "error_type": "missing_required_field",
            "message": (
                "contributors is required to create a post. "
                "Call fetch_authors to find valid author IDs, then include "
                "contributors as a comma-separated string (e.g. '12' or '12,15')."
            ),
            "retryable": False,
        }

    # Merge type-specific helper fields into meta_data before any validation.
    _META_HELPER_FIELDS = ("meta_video_url", "meta_video_embed", "meta_landscape_thumbnail")
    meta_extras = {f: payload.pop(f) for f in _META_HELPER_FIELDS if f in payload}
    if meta_extras:
        existing_meta = payload.get("meta_data") or {}
        payload["meta_data"] = {**existing_meta, **meta_extras}

    post_type = payload.get("type", "")

    # Video: if the user supplied a Featured Video URL but no iframe embed, build the
    # embed from the URL so a single user-provided media URL is enough to create the post.
    if post_type == "Video":
        meta = payload.get("meta_data") or {}
        if meta.get("meta_video_url") and not meta.get("meta_video_embed"):
            embed = _build_video_embed_from_url(meta["meta_video_url"])
            if embed:
                meta["meta_video_embed"] = embed
                payload["meta_data"] = meta

    # Gallery / Web Story: serialize structured image slides into the content blob the
    # dashboard editor AND public page read (content.data.gallery / content.data.web_story).
    # These helper arrays never go to the API as top-level fields, so pop them regardless
    # of type.
    gallery_images   = payload.pop("gallery_images", None)
    web_story_images = payload.pop("web_story_images", None)
    if post_type == "Gallery" and gallery_images:
        content_str, err = _build_gallery_content(credentials, gallery_images)
        if err is not None:
            return err
        payload["content"] = content_str
    if post_type == "Web Story" and web_story_images:
        content_str, err = _build_web_story_content(credentials, web_story_images)
        if err is not None:
            return err
        payload["content"] = content_str

    # Featured image: the CMS banner_url field stores the media-library object id (an
    # integer). _resolve_banner_url validates the id and returns it as an int; a path or
    # URL is rejected upstream as 'Banner URL must be a valid media object ID'.
    if payload.get("banner_url") is not None:
        resolved, err = _resolve_banner_url(credentials, payload["banner_url"])
        if err is not None:
            return err
        payload["banner_url"] = resolved

    # Draft Videos still hard-require a video source (embed or a URL we can embed). For
    # non-Draft Videos the friendly journey gate below handles a missing video instead.
    if (
        post_type == "Video"
        and _is_draft_status(payload.get("status"))
        and not (payload.get("meta_data") or {}).get("meta_video_embed")
    ):
        return {
            "error_type": "missing_required_field",
            "message": (
                "Video posts require a video source: pass meta_video_url (a YouTube/Vimeo/media URL — "
                "the iframe embed is built from it automatically) or meta_video_embed (raw <iframe> HTML). "
                "Both are merged into meta_data automatically."
            ),
            "retryable": False,
        }

    if post_type == "Web Story" and not payload.get("content") and not payload.get("custom_entity"):
        return {
            "error_type": "missing_required_field",
            "message": (
                "Web Story posts require slides. Pass web_story_images as an array of "
                "{img_src (media path) OR id (numeric media id), title, desc, alt_text}; "
                "the tool serializes them into content.data.web_story (the image-slide shape the "
                "dashboard and public page read — a real Web Story is image slides, NOT AMP markup). "
                "Alternatively pass raw AMP story markup in the 'content' field. "
                "meta_landscape_thumbnail is optional."
            ),
            "retryable": False,
        }
    if post_type == "Gallery" and not payload.get("content") and not payload.get("custom_entity"):
        return {
            "error_type": "missing_required_field",
            "message": (
                "Gallery posts require slides. Pass gallery_images as an array of "
                "{img_src (media path) OR id (numeric media id), title, desc, alt_text, caption_text}; "
                "the tool serializes them into content.data.gallery (the shape the dashboard 'Gallery Slides' "
                "editor and the public page both read). An empty gallery creates as a Draft but cannot be published."
            ),
            "retryable": False,
        }

    if post_type in ("Article", "Gallery"):
        payload.setdefault("after_para", 0)

    _coerce_post_int_fields(payload)
    _strip_list_brackets(payload)

    # Draft: create directly and immediately — no preview/confirmation step.
    if payload.get("status") == "Draft":
        return _remap_post_type_error(cms_client.post(credentials, "/post/", payload), post_type)

    # Post journey: before previewing a non-Draft Article/Video, make sure the user has
    # supplied everything the dashboard "Post Content" form expects. If not, return a
    # friendly checklist (NOT an error) so the client can collect it and come back.
    needs_input = _check_post_journey(payload, post_type)
    if needs_input is not None:
        return needs_input

    # Non-Draft (Published / Scheduled / Approval Pending): never write on the first call.
    # Show a preview of exactly what will be created and request explicit confirmation.
    # No draft is created here — this only renders the preview.
    if dry_run:
        status = payload.get("status")
        confirm_note = (
            f"\n  This will CREATE and immediately set the post LIVE (status '{status}')."
            if status == "Published"
            else f"\n   This will CREATE the post with status '{status}'."
        )
        preview = helpers.preview_create_op("Post", payload) + confirm_note + (
            "\nTo confirm, call create_post again with the same arguments and dry_run=false."
        )
        return {"dry_run": True, "preview": preview, "confirmation_required": True}

    # Preferred path: create directly in the intended (non-Draft) status with a single POST.
    # The backend supports this (a single POST with status=Published publishes e.g. a Video).
    # The two-step "POST as Draft → PATCH status" fallback below is kept only for the case
    # where a direct non-Draft POST is rejected with a 5xx, so no type can regress.
    intended_status = payload["status"]
    result = _remap_post_type_error(cms_client.post(credentials, "/post/", payload), post_type)

    no_data_hint = _no_data_type_hint(result, post_type)
    if no_data_hint is not None:
        return no_data_hint

    if not (isinstance(result, dict) and result.get("error_type") == "upstream_error"):
        return result

    # Direct create 5xx'd — fall back to the two-step flow. First check whether the 5xx
    # actually committed the post (reuse it rather than create a duplicate).
    existing = _find_recent_post_by_english_title(credentials, payload.get("english_title"))
    if existing is not None:
        post_id = existing.get("id")
    else:
        draft_result = _remap_post_type_error(
            cms_client.post(credentials, "/post/", {**payload, "status": "Draft"}), post_type
        )
        draft_hint = _no_data_type_hint(draft_result, post_type)
        if draft_hint is not None:
            return draft_hint
        if isinstance(draft_result, dict) and "error_type" in draft_result:
            return draft_result
        draft_data = draft_result.get("data", draft_result) if isinstance(draft_result, dict) else draft_result
        post_id = draft_data.get("id") if isinstance(draft_data, dict) else None

    if not post_id:
        return result

    patch = {"status": intended_status}
    if intended_status == "Scheduled" and payload.get("scheduled_at"):
        patch["scheduled_at"] = payload["scheduled_at"]

    patch_result = cms_client.patch(credentials, f"/post/{post_id}/", patch)
    if isinstance(patch_result, dict) and "error_type" in patch_result:
        return {
            "error_type": "partial_success",
            "message": (
                f"Post was created (ID: {post_id}) but setting status to "
                f"{intended_status} failed: {patch_result.get('message', 'unknown error')}. "
                "Use update_post to retry the status change."
            ),
            "post_id": post_id,
            "retryable": False,
        }

    return patch_result


def update_post(credentials: dict, args: dict):
    dry_run         = args.get("dry_run", True)
    confirm_publish = args.get("confirm_publish", False)
    post_id         = args["id"]
    changes         = {k: v for k, v in args.items() if k not in ("id", "dry_run", "confirm_publish") and v is not None and v != ""}

    # Gallery / Web Story: serialize structured image slides into content.data.gallery /
    # content.data.web_story (the blob the dashboard editor and public page read) before
    # the diff/patch. These helper arrays are never sent to the API as top-level fields.
    gallery_images   = changes.pop("gallery_images", None)
    web_story_images = changes.pop("web_story_images", None)
    if gallery_images:
        content_str, err = _build_gallery_content(credentials, gallery_images)
        if err is not None:
            return err
        changes["content"] = content_str
    if web_story_images:
        content_str, err = _build_web_story_content(credentials, web_story_images)
        if err is not None:
            return err
        changes["content"] = content_str

    # Featured image: the CMS banner_url field stores the media-library object id (int).
    if changes.get("banner_url") is not None:
        resolved, err = _resolve_banner_url(credentials, changes["banner_url"])
        if err is not None:
            return err
        changes["banner_url"] = resolved

    _coerce_post_int_fields(changes)
    _strip_list_brackets(changes)

    # Decide on the post's *effective* status: the incoming status if the caller is
    # changing it, otherwise the post's current status (costs one GET). Only "live"
    # statuses (Published/Scheduled/Approval Pending) go through dry_run — a Draft,
    # whether it stays a draft or is being set to one, is written immediately with no
    # preview. Editing an already-live post still previews (effective status is live).
    current = None
    if "status" in changes:
        effective_status = changes["status"]
    else:
        current = cms_client.get(credentials, f"/post/{post_id}/")
        if isinstance(current, dict) and "error_type" in current:
            return current
        effective_status = current.get("status") if isinstance(current, dict) else None

    if _is_draft_status(effective_status):
        return cms_client.patch(credentials, f"/post/{post_id}/", changes)

    if dry_run:
        if current is None:
            current = cms_client.get(credentials, f"/post/{post_id}/")
            if isinstance(current, dict) and "error_type" in current:
                return current
        return {"dry_run": True, "preview": helpers.preview_update_op("Post", post_id, current, changes)}

    if changes.get("status") == "Published" and not confirm_publish:
        return {
            "error_type": "confirmation_required",
            "message": (
                "Publishing a post requires confirm_publish=true. "
                "Call again with dry_run=false AND confirm_publish=true to publish."
            ),
            "retryable": False,
        }
    return cms_client.patch(credentials, f"/post/{post_id}/", changes)
