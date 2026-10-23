import pymysql
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from accounts.management.commands.import_wordpress_users import import_users, roles_for
from accounts.models import User
from shared.wp_migration.ids import user_id_from_wp_id
from shared.wp_migration.source import MariaDBSource, WPUser, connection_settings

pytestmark = pytest.mark.django_db


class FakeSource:
    def __init__(self, *users):
        self._users = list(users)

    def users(self):
        return list(self._users)


ADMIN = WPUser(1, "admin", "admin@example.com", "admin", ("administrator",))
SARAH = WPUser(2, "sarah_k", "sarah@example.com", "Sarah K.", ("author",))


class TestRoles:
    @pytest.mark.parametrize(
        ("wp_roles", "expected"),
        [
            (("administrator",), ["editor", "reader"]),
            (("editor",), ["editor", "reader"]),
            (("author",), ["reader"]),
            (("subscriber",), ["reader"]),
            ((), ["reader"]),
        ],
    )
    def test_wordpress_roles_map_to_auth_roles(self, wp_roles, expected):
        wp_user = WPUser(9, "x", "x@example.com", "X", wp_roles)

        assert sorted(roles_for(wp_user)) == expected


class TestImport:
    def test_creates_users_with_the_deterministic_id_and_no_password_without_a_hash(self):
        report = import_users(FakeSource(ADMIN, SARAH))

        assert report.created == 2
        sarah = User.objects.get(username="sarah_k")
        assert sarah.id == user_id_from_wp_id(2)
        assert (sarah.email, sarah.display_name) == ("sarah@example.com", "Sarah K.")
        assert not sarah.has_usable_password()
        assert sarah.role_names() == ["reader"]
        assert User.objects.get(username="admin").role_names() == ["editor", "reader"]

    def test_rerun_changes_nothing(self):
        import_users(FakeSource(ADMIN, SARAH))

        report = import_users(FakeSource(ADMIN, SARAH))

        assert (report.created, report.updated, report.unchanged) == (0, 0, 2)
        assert User.objects.count() == 2

    def test_a_changed_email_is_updated(self):
        import_users(FakeSource(SARAH))

        report = import_users(
            FakeSource(WPUser(2, "sarah_k", "new@example.com", "Sarah K.", ("author",)))
        )

        assert report.updated == 1
        assert User.objects.get(pk=user_id_from_wp_id(2)).email == "new@example.com"

    def test_a_rerun_does_not_undo_changes_made_in_this_service(self):
        import_users(FakeSource(ADMIN, SARAH))
        sarah = User.objects.get(pk=user_id_from_wp_id(2))
        sarah.set_password("chosen-here")
        sarah.save()
        sarah.roles.add(*User.objects.get(pk=user_id_from_wp_id(1)).roles.all())  # promoted in auth
        User.objects.get(pk=user_id_from_wp_id(1)).roles.clear()  # demoted in auth

        import_users(FakeSource(ADMIN, SARAH))

        sarah.refresh_from_db()
        assert sarah.check_password("chosen-here")
        assert sarah.role_names() == ["editor", "reader"]
        assert User.objects.get(pk=user_id_from_wp_id(1)).role_names() == []


class TestCommands:
    def test_set_dev_password_sets_a_usable_password(self, settings):
        settings.DEBUG = True
        import_users(FakeSource(SARAH))

        call_command("set_dev_password", "sarah_k", "pw")

        assert User.objects.get(username="sarah_k").check_password("pw")

    def test_set_dev_password_refuses_outside_debug(self, settings):
        settings.DEBUG = False
        import_users(FakeSource(SARAH))

        with pytest.raises(CommandError, match="DEBUG"):
            call_command("set_dev_password", "sarah_k", "pw")

        assert not User.objects.get(username="sarah_k").has_usable_password()

    def test_set_dev_password_for_an_unknown_user(self, settings):
        settings.DEBUG = True

        with pytest.raises(CommandError, match="No such user"):
            call_command("set_dev_password", "ghost", "pw")

    def test_rotate_signing_key_adds_a_key(self, capsys):
        from accounts.models import SigningKey

        call_command("rotate_signing_key")
        call_command("rotate_signing_key")

        assert SigningKey.objects.count() == 2
        assert "New signing key" in capsys.readouterr().out


@pytest.mark.integration
def test_imports_the_real_wordpress_users():
    config = connection_settings()
    try:
        pymysql.connect(
            host=config["host"],
            port=config["port"],
            user=config["user"],
            password=config["password"],
            database=config["database"],
            connect_timeout=2,
        ).close()
    except pymysql.err.OperationalError:
        pytest.skip("wp-db is not running (make wp-source)")

    report = import_users(MariaDBSource(**config))

    assert report.created == 9
    assert User.objects.get(username="admin").role_names() == ["editor", "reader"]
    assert User.objects.get(username="sarah_k").role_names() == ["reader"]
    assert User.objects.get(username="sarah_k").id == user_id_from_wp_id(2)
    # Every seeded user keeps their WordPress password (admin/admin, reviewers changeme).
    assert User.objects.get(username="admin").check_password("admin")
    assert User.objects.get(username="sarah_k").check_password("changeme")
    assert not User.objects.get(username="sarah_k").check_password("wrong")
    assert import_users(MariaDBSource(**config)).created == 0
