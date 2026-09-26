"""
Development settings for Policy-Driven Hostel Allocation Engine.
"""
from .base import *

DEBUG = True
ALLOWED_HOSTS = ["*"]


# Dev-specific apps
if "django_extensions" in INSTALLED_APPS:
    pass

# Email backend: print emails to console in development
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# In-memory or Redis caching for development
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-snowflake",
    }
}
