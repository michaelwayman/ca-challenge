from django.core.management.base import BaseCommand
from django.db import transaction

from accounts import keys, tokens


class Command(BaseCommand):
    help = (
        "Delete expired refresh tokens and long-retired signing keys. Safe to run at any "
        "time; meant to run on a schedule (cron, a Kubernetes CronJob)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Count, delete nothing.")

    def handle(self, *args, dry_run, **options):
        with transaction.atomic():
            refresh = tokens.purge_refresh_tokens(dry_run=dry_run)
            signing = keys.purge_retired_keys(dry_run=dry_run)
        verb = "Would delete" if dry_run else "Deleted"
        self.stdout.write(f"{verb} {refresh} refresh token(s) and {signing} signing key(s).")
