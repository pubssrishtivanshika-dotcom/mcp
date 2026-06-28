"""Post user journeys (mirror the dashboard "Post Content" form).

When a post is created in a non-Draft status, the journey is: gather everything the *user*
must choose before we show a preview, let the *AI* fill the suggestion fields, and validate
the two length rules the form enforces. If anything the user must supply is missing we
DON'T error — we return a friendly checklist so the client can ask for it and come back,
exactly like the dashboard form would block "Preview" until it's complete.
"""
import re

_TITLE_MIN = 10           # title must be at least 10 characters
_ENGLISH_TITLE_MAX = 250  # english_title must not exceed 250 characters


def _present(key):
    """A presence check for a top-level payload key."""
    return lambda p: bool(p.get(key))


def _meta_present(*keys):
    """A presence check for any of several keys inside payload['meta_data']."""
    return lambda p: any((p.get("meta_data") or {}).get(k) for k in keys)


# Each user field: (label, how-to-get-it, present_fn). The user picks/writes these.
# Each AI field: (key, what the AI should do when it's missing). Never blocks the preview.
_ARTICLE_USER_FIELDS = (
    ("a primary category",
     "ask the user to pick one (list options with list_editorial_categories)",
     _present("primary_category")),
    ("at least one contributor/author",
     "ask the user which author(s) to credit (list options with fetch_authors)",
     _present("contributors")),
    ("the article body",
     "ask the user for the post content (what they type/paste into the dashboard editor)",
     _present("content")),
    ("tags",
     "ask the user which tags to apply (list options with list_editorial_tags)",
     _present("tags")),
    ("a banner / featured image",
     "ask the user to select one from the media gallery (browse with list_media_assets)",
     _present("banner_url")),
    ("a short description (SEO meta description)",
     "ask the user, or offer to draft one from the content",
     _present("short_description")),
    ("a summary",
     "ask the user, or offer to draft one from the content",
     _present("summary")),
)
_ARTICLE_AI_FIELDS = (
    ("categories", "suggest additional categories only if there is a strong match"),
    ("seo_keyphrase", "suggest a focus keyphrase from the title/content"),
    ("banner_description", "derive one from the selected media asset's description"),
)

_VIDEO_USER_FIELDS = (
    ("a primary category",
     "ask the user to pick one (list options with list_editorial_categories)",
     _present("primary_category")),
    ("at least one contributor/author",
     "ask the user which author(s) to credit (list options with fetch_authors)",
     _present("contributors")),
    ("a custom thumbnail (an image)",
     "ask the user to choose an IMAGE from the media gallery (browse with list_media_assets) — passed as banner_url",
     _present("banner_url")),
    ("a featured video URL",
     "ask the user for the video's media URL (e.g. a YouTube/Vimeo link) as meta_video_url — I'll build the embed from it automatically",
     _meta_present("meta_video_url", "meta_video_embed")),
    ("the post content",
     "ask the user for the post content (what they type/paste into the dashboard editor)",
     _present("content")),
    ("tags",
     "ask the user which tags to apply (list options with list_editorial_tags)",
     _present("tags")),
    ("a short description (SEO meta description)",
     "ask the user, or offer to draft one from the content",
     _present("short_description")),
    ("a summary",
     "ask the user, or offer to draft one from the content",
     _present("summary")),
)
_VIDEO_AI_FIELDS = (
    ("banner_description", "write a caption for the featured video"),
    ("categories", "suggest additional categories only if there is a strong match (optional)"),
    ("seo_keyphrase", "suggest a focus keyphrase from the title/content"),
)

# Per-type journey: (label, user_fields, ai_fields). Only these types are gated.
_POST_JOURNEYS = {
    "Article": ("Article", _ARTICLE_USER_FIELDS, _ARTICLE_AI_FIELDS),
    "Video":   ("Video",   _VIDEO_USER_FIELDS,   _VIDEO_AI_FIELDS),
}


# YouTube (watch / youtu.be / embed / shorts) and Vimeo URL → canonical embed src.
_YOUTUBE_RE = re.compile(r"(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([A-Za-z0-9_-]{11})")
_VIMEO_RE   = re.compile(r"vimeo\.com/(?:video/)?(\d+)")


def _build_video_embed_from_url(url):
    """Build an <iframe> embed from a user-supplied video URL so a single Media URL is enough
    to create a Video post. Recognizes YouTube and Vimeo; any other http(s) URL is embedded
    directly. Returns the iframe HTML, or None if the URL is unusable."""
    if not isinstance(url, str) or not url.strip():
        return None
    u = url.strip()
    m = _YOUTUBE_RE.search(u)
    if m:
        src = f"https://www.youtube.com/embed/{m.group(1)}"
    elif _VIMEO_RE.search(u):
        src = f"https://player.vimeo.com/video/{_VIMEO_RE.search(u).group(1)}"
    elif u.startswith(("http://", "https://")):
        src = u
    else:
        return None
    return (
        f'<iframe src="{src}" width="560" height="315" frameborder="0" '
        'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" '
        'allowfullscreen></iframe>'
    )


def _check_post_journey(payload: dict, post_type: str):
    """For a gated non-Draft post type, return a friendly 'needs_input' checklist when the
    user still has fields to supply (or a length rule is broken); otherwise None to proceed.

    This is intentionally NOT an error_type — it's guidance the client surfaces to the user
    so they can complete the form before we render the create preview.
    """
    journey = _POST_JOURNEYS.get(post_type)
    if journey is None:
        return None
    label, user_fields, ai_fields = journey

    problems = []  # length-rule violations on values the user already gave
    title = payload.get("title")
    if isinstance(title, str) and 0 < len(title.strip()) < _TITLE_MIN:
        problems.append(
            f"title is too short — it must be at least {_TITLE_MIN} characters "
            f"(got {len(title.strip())}). Ask the user for a longer headline."
        )
    english_title = payload.get("english_title")
    if isinstance(english_title, str) and len(english_title.strip()) > _ENGLISH_TITLE_MAX:
        problems.append(
            f"english_title is too long — it must be at most {_ENGLISH_TITLE_MAX} "
            f"characters (got {len(english_title.strip())}). Ask the user to shorten it."
        )

    missing = [(label_, how) for label_, how, present in user_fields if not present(payload)]
    ai_todo = [(key, note) for key, note in ai_fields if not payload.get(key)]

    if not problems and not missing:
        return None

    lines = [f"Before I can preview this {label}, a few things still need your input:", ""]
    if problems:
        lines.append("Please fix:")
        lines += [f"  • {p}" for p in problems]
        lines.append("")
    if missing:
        lines.append("Please provide (the user chooses these):")
        lines += [f"  • {m_label} — {how}" for m_label, how in missing]
        lines.append("")
    if ai_todo:
        lines.append("I'll suggest these for you (no need to ask the user unless they want to set them):")
        lines += [f"  • {note}" for _, note in ai_todo]
        lines.append("")
    lines.append("Once you have these, call create_post again with them included to see the preview.")

    return {
        "needs_input": True,
        "message": "\n".join(lines),
        "missing_from_user": [m_label for m_label, _ in missing],
        "validation_issues": problems,
        "ai_will_suggest": [key for key, _ in ai_todo],
    }
