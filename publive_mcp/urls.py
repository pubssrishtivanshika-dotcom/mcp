from django.urls import include, path

urlpatterns = [
    path("", include("authentication.urls")),
    path("", include("mcp.urls")),
]
