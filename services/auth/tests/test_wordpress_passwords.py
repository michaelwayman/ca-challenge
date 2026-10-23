import bcrypt
import pytest
from django.contrib.auth.hashers import check_password

from accounts.hashers import WordPressPasswordHasher, encode_wordpress_hash, is_supported
from accounts.management.commands.import_wordpress_users import import_users
from accounts.models import User
from shared.wp_migration.source import WPUser

from .conftest import login

# Hashes from data/wordpress-dump.sql; the challenge's seed.sh set these passwords.
ADMIN_HASH = "$wp$2y$10$UpoCiOx5f0cvBvZXvokzSeDLPZhnBXxN/Bak5RFVHAYalQIzhR1GS"  # "admin"
SARAH_HASH = "$wp$2y$10$Bq5L2OfrIcvdrv.UniuFv.VcPL9.qAN4MdhoiYGTbYszBEkzhVVSy"  # "changeme"
PHPASS_HASH = "$P$BexampleexampleexampleexampleX/"  # pre-6.8 WordPress format, not supported


def wp_user(wp_id=1, login="admin", password_hash=ADMIN_HASH, roles=("administrator",)):
    return WPUser(wp_id, login, f"{login}@example.com", login, roles, password_hash)


class FakeSource:
    def __init__(self, *users):
        self._users = list(users)

    def users(self):
        return list(self._users)


class TestHasher:
    @pytest.mark.parametrize(
        ("wp_hash", "password"), [(ADMIN_HASH, "admin"), (SARAH_HASH, "changeme")]
    )
    def test_the_wordpress_password_verifies_and_others_do_not(self, wp_hash, password):
        encoded = encode_wordpress_hash(wp_hash)

        assert WordPressPasswordHasher().verify(password, encoded)
        assert not WordPressPasswordHasher().verify("wrong", encoded)

    def test_plain_bcrypt_as_wordpress_stores_it_verifies(self):
        wp_hash = bcrypt.hashpw(b"s3cret", bcrypt.gensalt(4)).decode().replace("$2b$", "$2y$", 1)

        assert WordPressPasswordHasher().verify("s3cret", encode_wordpress_hash(wp_hash))

    @pytest.mark.parametrize(
        "wp_hash", [PHPASS_HASH, "5f4dcc3b5aa765d61d8327deb882cf99", "$wp$2y$bad"]
    )
    def test_an_unsupported_or_malformed_hash_never_verifies(self, wp_hash):
        assert not WordPressPasswordHasher().verify("password", encode_wordpress_hash(wp_hash))

    def test_it_never_creates_hashes(self):
        with pytest.raises(NotImplementedError):
            WordPressPasswordHasher().encode("password", "salt")

    def test_the_summary_masks_the_hash(self):
        summary = WordPressPasswordHasher().safe_summary(encode_wordpress_hash(ADMIN_HASH))

        assert ADMIN_HASH not in str(summary)

    def test_supported_formats(self):
        assert is_supported(ADMIN_HASH)
        assert not is_supported(PHPASS_HASH)
        assert not is_supported("")


@pytest.mark.django_db
class TestImport:
    def test_a_user_keeps_their_wordpress_password(self):
        report = import_users(FakeSource(wp_user()))

        user = User.objects.get(username="admin")
        assert user.password == f"wordpress${ADMIN_HASH}"
        assert check_password("admin", user.password)
        assert report.passwords == 1

    def test_an_unsupported_hash_leaves_the_password_unusable_and_says_so(self):
        report = import_users(FakeSource(wp_user(password_hash=PHPASS_HASH)))

        assert not User.objects.get(username="admin").has_usable_password()
        assert report.passwords == 0
        assert report.warnings == [
            "user admin: unsupported WordPress password hash; password left unusable"
        ]

    def test_a_rerun_keeps_a_password_changed_here(self):
        import_users(FakeSource(wp_user()))
        user = User.objects.get(username="admin")
        user.set_password("changed-here")
        user.save()

        report = import_users(FakeSource(wp_user()))

        assert User.objects.get(username="admin").check_password("changed-here")
        assert (report.updated, report.unchanged, report.passwords) == (0, 1, 0)

    def test_a_rerun_fills_a_password_that_is_still_unusable(self):
        import_users(FakeSource(wp_user(password_hash="")))  # imported before hashes were read
        assert not User.objects.get(username="admin").has_usable_password()

        report = import_users(FakeSource(wp_user()))

        assert User.objects.get(username="admin").check_password("admin")
        assert (report.updated, report.passwords) == (1, 1)


@pytest.mark.django_db
class TestLogin:
    def test_the_wordpress_password_logs_in_and_is_upgraded(self, api):
        import_users(FakeSource(wp_user()))

        assert login(api, "admin", "admin").status_code == 200
        stored = User.objects.get(username="admin").password
        assert not stored.startswith("wordpress$")  # re-hashed with the preferred hasher
        assert login(api, "admin", "admin").status_code == 200
        assert login(api, "admin", "wrong").status_code == 401

    def test_with_the_real_hashers_the_upgrade_is_pbkdf2(self, api, settings):
        settings.PASSWORD_HASHERS = [
            "django.contrib.auth.hashers.PBKDF2PasswordHasher",
            "accounts.hashers.WordPressPasswordHasher",
        ]
        import_users(FakeSource(wp_user()))

        assert login(api, "admin", "admin").status_code == 200
        assert User.objects.get(username="admin").password.startswith("pbkdf2_sha256$")
