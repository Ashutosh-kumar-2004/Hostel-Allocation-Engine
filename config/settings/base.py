"""
Base settings for Policy-Driven Hostel Allocation Engine.
"""
from pathlib import Path
import os
import environ

# Compatibility shim: django-libsql-backend compatibility across Django 5.x
import django.db.models
if not hasattr(django.db.models, "CompositePrimaryKey"):
    django.db.models.CompositePrimaryKey = None

# Base Directory: Points to root of the repo (where manage.py resides)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    ENVIRONMENT=(str, "development"),
    DEBUG=(bool, False),
    SECRET_KEY=(str, "django-insecure-default-change-me"),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1", ".onrender.com", "*"]),
    TURSO_DATABASE_URL=(str, ""),
    TURSO_AUTH_TOKEN=(str, ""),
    DATABASE_URL=(str, f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
    REDIS_URL=(str, "redis://localhost:6379/0"),
    CELERY_BROKER_URL=(str, "redis://localhost:6379/1"),
    CELERY_RESULT_BACKEND=(str, "redis://localhost:6379/2"),
    DEFAULT_INSTITUTION_ID=(str, "inst_default"),
)

# Take environment variables from .env file if present
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
DEFAULT_INSTITUTION_ID = env("DEFAULT_INSTITUTION_ID")
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=["https://*.onrender.com", "http://localhost:8000", "http://127.0.0.1:8000"]
)

# Application definition
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
]

LOCAL_APPS = [
    "apps.core",
    "apps.audit",
    "apps.inventory",
    "apps.applications",
    "apps.eligibility",
    "apps.preferences",
    "apps.compatibility",
    "apps.allocation",
    "apps.review",
    "apps.waitlist",
    "apps.publication",
    "apps.notifications",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.AutoSeedMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.user_roles",
                "apps.notifications.context_processors.notifications_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database configuration: Environment-driven database selection
# ENVIRONMENT=development -> local SQLite database (db.sqlite3)
# Any other value (especially 'production') -> Turso / libSQL database
ENVIRONMENT = (os.environ.get("ENVIRONMENT") or env("ENVIRONMENT", default="development")).strip().lower()

if ENVIRONMENT == "development":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    turso_url = (os.environ.get("TURSO_DATABASE_URL") or env("TURSO_DATABASE_URL", default="") or os.environ.get("DATABASE_URL") or "").strip()
    turso_token = (os.environ.get("TURSO_AUTH_TOKEN") or env("TURSO_AUTH_TOKEN", default="")).strip()

    if not turso_url:
        raise ValueError(
            "Configuration Error: When ENVIRONMENT is not 'development' (e.g., 'production'), "
            "the TURSO_DATABASE_URL environment variable must be set to your Turso/libSQL database URL."
        )

    DATABASES = {
        "default": {
            "ENGINE": "django_libsql",
            "NAME": turso_url,
            "AUTH_TOKEN": turso_token,
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Media files
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Celery Settings
CELERY_BROKER_URL = env("CELERY_BROKER_URL")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

# Authentication
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"

