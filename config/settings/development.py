"""Local development settings."""

from .base import *  # noqa: F403

DEBUG = True

ALLOWED_HOSTS = ["*"]

# Log outgoing email to the console during development.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
