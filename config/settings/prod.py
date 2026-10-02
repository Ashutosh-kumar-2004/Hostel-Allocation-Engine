"""
Production settings for Policy-Driven Hostel Allocation Engine.
"""
from .base import *

DEBUG = False

# Strict security settings
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=False)
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=False)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=False)
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
X_FRAME_OPTIONS = "DENY"

# Cache: Only use Redis if an explicit, non-local URL is configured; otherwise use ultra-fast LocMemCache
redis_url = env("REDIS_URL", default="").strip()
if redis_url and not redis_url.startswith("redis://localhost") and not redis_url.startswith("redis://127.0.0.1"):
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": redis_url,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "prod-cache-fallback",
        }
    }

# WhiteNoise compressed static files storage
STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"

