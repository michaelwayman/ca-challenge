"""One-off import of WordPress users. Re-runnable: rows are matched on the deterministic
id derived from the WordPress user id (ca_authlib.ids), the same one the main app uses
for its Reviewer rows."""

import os
import re
from dataclasses import dataclass, field
from typing import Protocol

import pymysql
import pymysql.cursors

from accounts.models import Role as RoleModel
from accounts.models import User
from ca_authlib.claims import Role
from ca_authlib.ids import user_id_from_wp_id

# WordPress roles that can edit content become editors; everyone can read.
EDITOR_WP_ROLES = {"administrator", "editor"}


@dataclass(frozen=True)
class WPUser:
    wp_id: int
    login: str
    email: str
    display_name: str
    wp_roles: tuple[str, ...]


class UserSource(Protocol):
    def users(self) -> list[WPUser]: ...


def connection_settings() -> dict:
    """Where the WordPress database is (compose profile `migration-source`; port 3307 is the
    host-side mapping). Read from the environment, so nothing else in the project knows."""
    return {
        "host": os.environ.get("WP_DB_HOST", "127.0.0.1"),
        "port": int(os.environ.get("WP_DB_PORT", "3307")),
        "user": os.environ.get("WP_DB_USER", "wp"),
        "password": os.environ.get("WP_DB_PASSWORD", "wp"),
        "database": os.environ.get("WP_DB_NAME", "wp"),
        "table_prefix": os.environ.get("WP_TABLE_PREFIX", "wp_"),
    }


class MariaDBUserSource:
    def __init__(self, *, host, port, user, password, database, table_prefix="wp_"):
        if not re.fullmatch(r"[A-Za-z0-9_]*", table_prefix):
            raise ValueError(f"invalid table prefix: {table_prefix!r}")
        self._args = {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "database": database,
            "charset": "utf8mb4",
            "cursorclass": pymysql.cursors.DictCursor,
        }
        self._prefix = table_prefix

    @classmethod
    def from_env(cls) -> "MariaDBUserSource":
        return cls(**connection_settings())

    def users(self) -> list[WPUser]:
        with pymysql.connect(**self._args) as conn, conn.cursor() as cursor:
            cursor.execute(
                f"SELECT ID, user_login, user_email, display_name FROM `{self._prefix}users` "  # noqa: S608
                "ORDER BY ID"
            )
            rows = cursor.fetchall()
            cursor.execute(
                f"SELECT user_id, meta_value FROM `{self._prefix}usermeta` WHERE meta_key = %s",  # noqa: S608
                (f"{self._prefix}capabilities",),
            )
            capabilities = {r["user_id"]: r["meta_value"] or "" for r in cursor.fetchall()}
        return [
            WPUser(
                wp_id=r["ID"],
                login=r["user_login"],
                email=r["user_email"],
                display_name=r["display_name"],
                # PHP-serialized, e.g. a:1:{s:13:"administrator";b:1;}
                wp_roles=tuple(re.findall(r's:\d+:"([^"]+)";b:1', capabilities.get(r["ID"], ""))),
            )
            for r in rows
        ]


@dataclass
class UserImportReport:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    warnings: list[str] = field(default_factory=list)


def roles_for(wp_user: WPUser) -> list[str]:
    roles = [Role.READER]
    if EDITOR_WP_ROLES & set(wp_user.wp_roles):
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
