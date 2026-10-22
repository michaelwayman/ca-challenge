import os
from pathlib import Path

from ca_authlib.claims import AUDIENCE_APP, ISSUER

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.auth",  # DRF's AnonymousUser for unauthenticated requests
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "rest_framework",
    "catalog",
]

# No sessions, cookies or CSRF: nothing signs in to this service. The API uses bearer tokens.
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
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
        "NAME": os.environ.get("DB_NAME", "app"),
        "USER": os.environ.get("DB_USER", "app"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "app"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5433"),
    }
}

# Reads are public; write endpoints add token authentication per view.
REST_FRAMEWORK = {
    # JSON only: no form-encoded or multipart bodies, which a browser can send cross-site.
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
STATIC_URL = "static/"
# Compiled assets (the stylesheet and the <BrandList /> bundle). A host build in static/
# (`make assets`, `make css-watch`) comes first, so it overrides the copy the Docker image
# compiled into ASSETS_DIR. static/ is always listed even when it does not exist yet, so a
# build created while the server is running is picked up without a restart.
STATICFILES_DIRS = [BASE_DIR / "static"]
if os.environ.get("ASSETS_DIR"):
    STATICFILES_DIRS.append(Path(os.environ["ASSETS_DIR"]))
SILENCED_SYSTEM_CHECKS = ["staticfiles.W004"]  # a listed directory that does not exist (yet)
USE_TZ = True
TIME_ZONE = "UTC"

# Token handling. Tokens are verified locally against the auth service's published keys;
# only the write endpoint also asks it (introspection) for the user's current roles.
CA_AUTH = {
    "JWKS_URL": os.environ.get("AUTH_JWKS_URL", "http://localhost:8001/.well-known/jwks.json"),
    "ISSUER": ISSUER,
    "AUDIENCE": AUDIENCE_APP,
    "ACCEPTED_TOKEN_VERSIONS": [1],
    "INTROSPECTOR": "catalog.auth.introspect",
}
AUTH_INTROSPECT_URL = os.environ.get(
    "AUTH_INTROSPECT_URL", "http://localhost:8001/api/auth/v1/introspect/"
)
# Dev default so compose works out of the box; must match the auth service's.
AUTH_SERVICE_SECRET = os.environ.get("AUTH_SERVICE_SECRET", "dev-service-secret")
AUTH_TIMEOUT_SECONDS = 2.0
