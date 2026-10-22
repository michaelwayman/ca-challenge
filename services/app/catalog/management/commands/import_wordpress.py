from django.core.management.base import BaseCommand, CommandError

from .wp_migration.importer import Importer, PruneRefused
from .wp_migration.source import MariaDBSource


class Command(BaseCommand):
    help = (
        "Import brands, reviews, industries and reviewers from the WordPress database. "
        "Safe to re-run: rows are matched on wp_id."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Do the full import, then roll it back."
        )
        parser.add_argument(
            "--prune",
            action="store_true",
            help="Also delete imported rows that no longer exist in WordPress.",
        )

    def handle(self, *args, dry_run, prune, **options):
        source = MariaDBSource.from_env()
        try:
            report = Importer(source, prune=prune, dry_run=dry_run).run()
        except PruneRefused as exc:
            raise CommandError(str(exc)) from exc

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run: nothing was saved."))
        for label, c in report.counts.items():
            self.stdout.write(
                f"{label:<10} created {c.created:>3}  updated {c.updated:>3}  "
                f"unchanged {c.unchanged:>3}  skipped {c.skipped:>3}  pruned {c.pruned:>3}"
            )
        for warning in report.warnings:
            self.stderr.write(self.style.WARNING(f"warning: {warning}"))
