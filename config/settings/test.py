"""Test settings.

These are used by pytest. Redis-backed channel layers are replaced with an
in-memory layer so tests do not require a running Redis. PostgreSQL is still
required because the domain relies on real constraints and row locking.
"""

from .base import *  # noqa: F403

DEBUG = False

# WhiteNoise is not needed under test and its staticfiles directory may not
# exist in a fresh checkout.
MIDDLEWARE = [m for m in MIDDLEWARE if "whitenoise" not in m]  # noqa: F405

CHANNEL_LAYERS = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
}

# Celery runs eagerly in tests: tasks execute inline and results are returned
# directly, which keeps the outbox/task boundary testable without a broker.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Keep logs quiet and deterministic.
LOGGING_CONFIG = None
