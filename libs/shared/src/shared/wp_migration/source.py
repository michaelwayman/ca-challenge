"""Reads the WordPress site being migrated, straight from its MariaDB database.

Both importers use it: the main app reads industries, brands, reviews and the authors' names;
the auth service reads the users with their roles. Nothing here touches a Django model; each
service's import command turns these rows into its own.
"""

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

import pymysql
import pymysql.cursors

BRAND_META_KEYS = (
    "website_url",
    "founded_year",
    "headquarters",
    "_yoast_wpseo_title",
    "_yoast_wpseo_metadesc",
)
REVIEW_META_KEYS = ("rating", "reviewer_name", "reviewer_location", "brand")


@dataclass(frozen=True)
class WPTerm:
    wp_id: int
    name: str
    slug: str


@dataclass(frozen=True)
class WPUser:
    wp_id: int
    login: str
    email: str
    display_name: str
    roles: tuple[str, ...] = ()  # WordPress roles, e.g. ("administrator",)


@dataclass(frozen=True)
class WPPost:
    wp_id: int
    slug: str
    title: str
    content: str
    published_gmt: datetime  # naive, UTC
    author_id: int
    meta: dict[str, str] = field(default_factory=dict)


class WordPressSource(Protocol):
    def industries(self) -> list[WPTerm]: ...
    def brands(self) -> list[WPPost]: ...
    def reviews(self) -> list[WPPost]: ...
    def users(self) -> list[WPUser]: ...
    def brand_industries(self) -> dict[int, list[int]]:
        """Brand wp_id -> industry term ids."""
        ...


def parse_capabilities(serialized: str) -> tuple[str, ...]:
    """The roles granted in a `wp_capabilities` value, which PHP serializes, e.g.
    `a:1:{s:13:"administrator";b:1;}`. Roles stored with `b:0` are not granted."""
    return tuple(re.findall(r's:\d+:"([^"]+)";b:1', serialized or ""))


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


class MariaDBSource:
    """Reads published content straight from the WordPress database."""

    def __init__(self, *, host, port, user, password, database, table_prefix="wp_"):
        if not re.fullmatch(r"[A-Za-z0-9_]*", table_prefix):
            raise ValueError(f"invalid table prefix: {table_prefix!r}")
        self._connect_args = {
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
    def from_env(cls) -> "MariaDBSource":
        return cls(**connection_settings())

    def _table(self, name: str) -> str:
        return f"`{self._prefix}{name}`"

    def _query(self, sql: str, params: tuple = ()) -> list[dict]:
        with pymysql.connect(**self._connect_args) as conn, conn.cursor() as cursor:
            cursor.execute(sql, params)
            return list(cursor.fetchall())

    def industries(self) -> list[WPTerm]:
        rows = self._query(
            f"SELECT t.term_id, t.name, t.slug FROM {self._table('terms')} t "  # noqa: S608
            f"JOIN {self._table('term_taxonomy')} tt ON tt.term_id = t.term_id "
            "WHERE tt.taxonomy = 'industry' ORDER BY t.term_id"
        )
        return [WPTerm(r["term_id"], r["name"], r["slug"]) for r in rows]

    def brand_industries(self) -> dict[int, list[int]]:
        rows = self._query(
            f"SELECT tr.object_id, tt.term_id FROM {self._table('term_relationships')} tr "  # noqa: S608
            f"JOIN {self._table('term_taxonomy')} tt "
            "ON tt.term_taxonomy_id = tr.term_taxonomy_id "
            "WHERE tt.taxonomy = 'industry' ORDER BY tr.object_id, tt.term_id"
        )
        links: dict[int, list[int]] = {}
        for r in rows:
            links.setdefault(r["object_id"], []).append(r["term_id"])
        return links

    def users(self) -> list[WPUser]:
        rows = self._query(
            f"SELECT ID, user_login, user_email, display_name FROM {self._table('users')} "  # noqa: S608
            "ORDER BY ID"
        )
        capabilities = {
            r["user_id"]: r["meta_value"] or ""
            for r in self._query(
                f"SELECT user_id, meta_value FROM {self._table('usermeta')} "  # noqa: S608
                "WHERE meta_key = %s",
                (f"{self._prefix}capabilities",),
            )
        }
        return [
            WPUser(
                wp_id=r["ID"],
                login=r["user_login"],
                email=r["user_email"],
                display_name=r["display_name"],
                roles=parse_capabilities(capabilities.get(r["ID"], "")),
            )
            for r in rows
        ]

    def brands(self) -> list[WPPost]:
        return self._posts("brand", BRAND_META_KEYS)

    def reviews(self) -> list[WPPost]:
        return self._posts("review", REVIEW_META_KEYS)

    def _posts(self, post_type: str, meta_keys: tuple[str, ...]) -> list[WPPost]:
        posts = self._table("posts")
        rows = self._query(
            "SELECT ID, post_name, post_title, post_content, post_date_gmt, post_author "  # noqa: S608
            f"FROM {posts} WHERE post_type = %s AND post_status = 'publish' ORDER BY ID",
            (post_type,),
        )
        placeholders = ", ".join(["%s"] * len(meta_keys))
        meta: dict[int, dict[str, str]] = {}
        meta_rows = self._query(
            "SELECT m.post_id, m.meta_key, m.meta_value "  # noqa: S608
            f"FROM {self._table('postmeta')} m JOIN {posts} p ON p.ID = m.post_id "
            "WHERE p.post_type = %s AND p.post_status = 'publish' "
            f"AND m.meta_key IN ({placeholders}) ORDER BY m.meta_id",
            (post_type, *meta_keys),
        )
        for r in meta_rows:
            meta.setdefault(r["post_id"], {})[r["meta_key"]] = r["meta_value"] or ""
        return [
            WPPost(
                wp_id=r["ID"],
                slug=r["post_name"],
                title=r["post_title"],
                content=r["post_content"],
                published_gmt=r["post_date_gmt"],
                author_id=r["post_author"],
                meta=meta.get(r["ID"], {}),
            )
            for r in rows
        ]
