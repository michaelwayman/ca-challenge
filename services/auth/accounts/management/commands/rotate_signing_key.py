from django.core.management.base import BaseCommand

from accounts import keys


class Command(BaseCommand):
    help = (
        "Create a new signing key; it starts signing at once and the old keys stay "
        "published. Run again with --retire-old after one access-token lifetime to "
        "stop publishing keys that no longer sign."
    )

    def add_arguments(self, parser):
        parser.add_argument("--retire-old", action="store_true", help="Retire stale keys only.")

    def handle(self, *args, retire_old, **options):
        if retire_old:
            self.stdout.write(f"Retired {keys.retire_old_keys()} key(s).")
            return
        key = keys.create_key()
        self.stdout.write(f"New signing key: {key.kid}")
