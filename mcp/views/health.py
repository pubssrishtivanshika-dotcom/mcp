import logging

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.views import View

from mcp.protocol.session import LATEST_PROTOCOL_VERSION

logger = logging.getLogger(__name__)


class HealthCheckView(View):
    """Liveness probe — dependency-free (no DB, no session). The load balancer probes this."""

    def get(self, request):
        return JsonResponse({
            "status":   "ok",
            "service":  "publive-mcp",
            "version":  settings.SERVER_VERSION,
            "protocol": LATEST_PROTOCOL_VERSION,
        })
