"""Deterministic user ids for users migrated from WordPress.

Both services import this so the auth importer and the main-app importer agree
on a migrated user's id without calling each other. Users created later get
random uuid4 ids; consumers treat every id as opaque.

This exists for the WordPress migration. Once nothing depends on it, a future
maintainer may delete it.
"""

import uuid

# Never change this: it would re-key every migrated user.
WP_USER_NAMESPACE = uuid.UUID("0ec28230-7470-44d6-9a1f-f82ba1ed34e6")


def user_id_from_wp_id(wp_id: int) -> uuid.UUID:
    return uuid.uuid5(WP_USER_NAMESPACE, f"wp-user:{wp_id}")
