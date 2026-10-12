"""ASGI entrypoint.

Serves the Django Ninja HTTP application. A WebSocket routing layer can be
added here once agent real-time updates are implemented.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

application = get_asgi_application()
