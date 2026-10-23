"""manage.py import_wordpress_users: create the WordPress users in this service.

Reading WordPress is shared code (shared.wp_migration.source); deciding which users and roles
exist here is this service's job, and lives here. Re-runnable: rows are matched on the
deterministic id derived from the WordPress user id (shared.wp_migration.ids), the same one the
main app uses for its Reviewer rows.
"""

from dataclasses import dataclass, field
from typing import Protocol

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Role as RoleModel
from accounts.models import User
from shared.auth.claims import Role
from shared.wp_migration.ids import user_id_from_wp_id
from shared.wp_migration.source import MariaDBSource, WPUser

# WordPress roles that can edit content become editors; everyone can read.
EDITOR_WP_ROLES = {"administrator", "editor"}


class UserSource(Protocol):
    """The part of shared.wp_migration.source.WordPressSource this import reads."""

    def users(self) -> list[WPUser]: ...


@dataclass
class UserImportReport:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    warnings: list[str] = field(default_factory=list)


def roles_for(wp_user: WPUser) -> list[str]:
    roles = [Role.READER]
    if EDITOR_WP_ROLES & set(wp_user.roles):
        roles.append(Role.EDITOR)
    return [str(r) for r in roles]


def import_users(source: UserSource) -> UserImportReport:
    """Create or update users. Passwords start unusable, and roles are set only when a
    user is created: after that, who holds which role is this service's to decide, so a
    re-run must not undo a grant or revoke made here."""
    report = UserImportReport()
    roles = {r.name: r for r in RoleModel.objects.all()}
    for wp_user in source.users():
        values = {
            "username": wp_user.login,
            "email": wp_user.email,
            "display_name": wp_user.display_name,
        }
        user = User.objects.filter(pk=user_id_from_wp_id(wp_user.wp_id)).first()
        if user is None:
            user = User(id=user_id_from_wp_id(wp_user.wp_id), **values)
            user.set_unusable_password()
            user.save()
            user.roles.set([roles[name] for name in roles_for(wp_user)])
            report.created += 1
            continue
        changed = [k for k, v in values.items() if getattr(user, k) != v]
        if changed:
            for k in changed:
                setattr(user, k, values[k])
            user.save(update_fields=changed)
            report.updated += 1
        else:
            report.unchanged += 1
    return report


class Command(BaseCommand):
    help = (
        "Import WordPress users with unusable passwords. Safe to re-run; roles and "
        "passwords of existing users are left alone."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Do the import, then roll back.")

    def handle(self, *args, dry_run, **options):
        with transaction.atomic():
            report = import_users(MariaDBSource.from_env())
            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING("Dry run: nothing was saved."))
        self.stdout.write(
            f"users  created {report.created:>3}  updated {report.updated:>3}  "
            f"unchanged {report.unchanged:>3}"
        )
