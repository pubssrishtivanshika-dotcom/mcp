from django.urls import path

from mcp.views import MCPEndpointView
from mcp.views.health import HealthCheckView

urlpatterns = [
    path("",       HealthCheckView.as_view(), name="health_check"),
    path("mcp",    MCPEndpointView.as_view(), name="mcp_endpoint"),
]
