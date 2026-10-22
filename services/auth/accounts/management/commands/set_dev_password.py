from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.models import User


class Command(BaseCommand):
    help = "Set a user's password. Development only: refuses to run when DEBUG is off."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("password")

    def handle(self, *args, username, password, **options):
        if not settings.DEBUG:
            raise CommandError("set_dev_password only runs with DEBUG on.")
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise CommandError(f"No such user: {username}") from exc
        user.set_password(password)
        user.save(update_fields=["password"])
        self.stdout.write(f"Password set for {username}.")
