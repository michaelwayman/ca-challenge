import uuid

from shared.wp_migration.ids import user_id_from_wp_id


def test_same_wp_id_gives_same_uuid():
    assert user_id_from_wp_id(2) == user_id_from_wp_id(2)


def test_different_wp_ids_give_different_uuids():
    assert user_id_from_wp_id(2) != user_id_from_wp_id(3)


def test_id_is_a_version_5_uuid():
    assert user_id_from_wp_id(2).version == 5


def test_id_is_pinned():
    # Guards against an accidental namespace change re-keying migrated users.
    assert user_id_from_wp_id(1) == uuid.UUID("2ecd0d83-d3c7-516a-aee9-b4e8aecd807c")
