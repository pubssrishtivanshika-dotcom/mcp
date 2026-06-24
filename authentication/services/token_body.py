# Responsibility: Parse the /oauth/token request body (JSON or form-urlencoded).
import json
from typing import Any, Optional
from urllib.parse import parse_qs

from django.http import HttpRequest, JsonResponse


class TokenBodyMixin:
    """OAuth token-endpoint body parsing for the auth service."""

    def parse_oauth_token_body(self, request: HttpRequest) -> tuple[Optional[dict[str, Any]], Optional[JsonResponse]]:
        """Parse /oauth/token request body from JSON or application/x-www-form-urlencoded."""
        content_type = (request.content_type or "").split(";", 1)[0].strip().lower()

        if content_type == "application/json":
            try:
                body = json.loads(request.body)
            except json.JSONDecodeError:
                return None, JsonResponse({"error": "invalid_request"}, status=400)
            if not isinstance(body, dict):
                return None, JsonResponse({"error": "invalid_request"}, status=400)
            return body, None

        if content_type == "application/x-www-form-urlencoded":
            if request.POST:
                return request.POST.dict(), None
            try:
                parsed = parse_qs(request.body.decode("utf-8"), keep_blank_values=True)
            except UnicodeDecodeError:
                return None, JsonResponse({"error": "invalid_request"}, status=400)
            return {key: values[0] if values else "" for key, values in parsed.items()}, None

        return None, JsonResponse(
            {
                "error": "invalid_request",
                "error_description": "Content-Type must be application/x-www-form-urlencoded or application/json",
            },
            status=400,
        )
