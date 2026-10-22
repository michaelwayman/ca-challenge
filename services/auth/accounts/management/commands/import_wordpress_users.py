from django.core.management.base import BaseCommand
from django.db import transaction

from .wp_migration.users import MariaDBUserSource, import_users


class Command(BaseCommand):
    help = (
        "Import WordPress users with unusable passwords. Safe to re-run; roles and "
        "passwords of existing users are left alone."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Do the import, then roll back.")

    def handle(self, *args, dry_run, **options):
        with transaction.atomic():
            report = import_users(MariaDBUserSource.from_env())
            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING("Dry run: nothing was saved."))
        self.stdout.write(
            f"users  created {report.created:>3}  updated {report.updated:>3}  "
            f"unchanged {report.unchanged:>3}"
        )
