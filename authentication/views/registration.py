# Responsibility: OAuth 2.0 dynamic client registration endpoint.
import json
import logging
import secrets
from typing import Optional

from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from authentication.models import OAuthClient
from authentication.services import auth_service

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class OAuthRegisterView(View):
    """Register a new OAuth 2.0 client dynamically (one redirect_uri per client)."""

    def post(self, request: HttpRequest) -> JsonResponse:
        origin_err: Optional[JsonResponse] = auth_service.check_origin(request)
        if origin_err:
            return origin_err

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            body = {}

        # Accept either redirect_uris (list, legacy) or redirect_uri (string).
        raw_uris = body.get("redirect_uris", [])
        if isinstance(raw_uris, list) and raw_uris:
            redirect_uri: str = raw_uris[0]
        else:
            redirect_uri = str(body.get("redirect_uri", "")).strip()

        if redirect_uri and not auth_service.is_registrable_redirect_uri(redirect_uri):
            logger.warning("OAuth register: insecure redirect_uri=%s", redirect_uri)
            return JsonResponse(
                {
                    "error": "invalid_redirect_uri",
                    "error_description": "redirect_uri must use https:// or be a loopback address (http://localhost or http://127.0.0.1)",
                },
                status=400,
            )

        # os.urandom under the hood
        client_id: str = secrets.token_urlsafe(24)

        try:
            OAuthClient.objects.create_client(
                client_id=client_id,
                redirect_uri=redirect_uri,
            )
            logger.info("OAuth client registered: client_id=%s redirect_uri=%s", client_id, redirect_uri)
            return JsonResponse({
                "client_id": client_id,
                "client_id_issued_at": int(timezone.now().timestamp()),
                "redirect_uris": [redirect_uri] if redirect_uri else [],
            }, status=201)
        except Exception:
            logger.error("OAuth client registration failed", exc_info=True)
            raise
