from django.apps import AppConfig
from authentication.cors import register_cors_signal

class AuthenticationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "authentication"

    def ready(self) -> None:
        register_cors_signal()