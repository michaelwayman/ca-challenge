import os
from pathlib import Path

from ca_authlib.claims import AUDIENCE_APP

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "accounts",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Sessions and CSRF exist only for the admin site; the JSON API uses bearer tokens (DRF views
# are CSRF-exempt). Cookies are shared across ports on one host, so the cookies get names of
# their own rather than Django's generic ones.
SESSION_COOKIE_NAME = "auth_sessionid"
CSRF_COOKIE_NAME = "auth_csrftoken"
SESSION_COOKIE_AGE = 3600  # one hour

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# Defaults target the Postgres port published on the host so `uv run` works
# outside Docker; compose overrides these to reach the container directly.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "auth"),
        "USER": os.environ.get("DB_USER", "auth"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "auth"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5434"),
    }
}

AUTH_USER_MODEL = "accounts.User"

# Reads of nothing here are public except through explicit views; no sessions or cookies.
REST_FRAMEWORK = {
    # JSON only: no form-encoded or multipart bodies, which a browser can send cross-site.
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
}

ACCESS_TOKEN_TTL = 600  # seconds
REFRESH_TOKEN_TTL = 7 * 24 * 3600

# Services that tokens may be issued for, and which token version each one is sent.
# Moving a service to a new version is changing its number here (see DECISIONS.md D8d).
AUDIENCES = {
    AUDIENCE_APP: {"token_version": int(os.environ.get("AUTH_TOKEN_VERSION_APP", "1"))},
}

# Shared with the services allowed to call /introspect/. A dev default so compose works
# out of the box; set a real one anywhere else.
SERVICE_SECRET = os.environ.get("AUTH_SERVICE_SECRET", "dev-service-secret")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
STATIC_URL = "static/"
USE_TZ = True
TIME_ZONE = "UTC"
