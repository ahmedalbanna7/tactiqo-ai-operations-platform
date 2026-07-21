"""ASGI entrypoint built from environment-backed settings."""

from tactiqo.shared.infrastructure.settings import Settings
from tactiqo_api.factory import create_app

app = create_app(Settings())
