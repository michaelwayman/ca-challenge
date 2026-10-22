import django
from django.conf import settings

if not settings.configured:
    settings.configure(
        SECRET_KEY="test",  # noqa: S106
        INSTALLED_APPS=["rest_framework"],
        REST_FRAMEWORK={"UNAUTHENTICATED_USER": None},
        CA_AUTH={},
    )
    django.setup()
