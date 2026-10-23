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

from accounts.hashers import encode_wordpress_hash, is_supported
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
    passwords: int = 0  # users whose password was set from their WordPress hash
    warnings: list[str] = field(default_factory=list)


def roles_for(wp_user: WPUser) -> list[str]:
    roles = [Role.READER]
    if EDITOR_WP_ROLES & set(wp_user.roles):
        roles.append(Role.EDITOR)
    return [str(r) for r in roles]


def _take_wordpress_password(user: User, wp_user: WPUser, report: UserImportReport) -> bool:
    """Give `user` their WordPress password hash, verified at login by
    accounts.hashers.WordPressPasswordHasher and replaced by a PBKDF2 hash on the first
    successful login. A format that cannot be verified leaves the password unusable."""
    if not wp_user.password_hash:
        return False
    if not is_supported(wp_user.password_hash):
        report.warnings.append(
            f"user {wp_user.login}: unsupported WordPress password hash; password left unusable"
        )
        return False
    user.password = encode_wordpress_hash(wp_user.password_hash)
    report.passwords += 1
    return True


def import_users(source: UserSource) -> UserImportReport:
    """Create or update users. Roles and passwords are set when a user is created: after
    that, who holds which role and what the password is are this service's to decide, so a
    re-run must not undo a grant, a revoke or a password change made here. The one
    exception: a user whose password is still unusable gets their WordPress hash."""
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
            if not _take_wordpress_password(user, wp_user, report):
                user.set_unusable_password()
            user.save()
            user.roles.set([roles[name] for name in roles_for(wp_user)])
            report.created += 1
            continue
        changed = [k for k, v in values.items() if getattr(user, k) != v]
        if not user.has_usable_password() and _take_wordpress_password(user, wp_user, report):
            changed.append("password")
        if changed:
            for k in changed:
                if k in values:
                    setattr(user, k, values[k])
            user.save(update_fields=changed)
            report.updated += 1
        else:
            report.unchanged += 1
    return report


class Command(BaseCommand):
    help = (
        "Import WordPress users with their WordPress passwords. Safe to re-run; roles and "
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
            f"unchanged {report.unchanged:>3}  passwords from WordPress {report.passwords:>3}"
        )
        for warning in report.warnings:
            self.stderr.write(self.style.WARNING(f"warning: {warning}"))
