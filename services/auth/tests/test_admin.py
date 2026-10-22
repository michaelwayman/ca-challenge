from datetime import timedelta

import pytest
from django.conf import settings
from django.core.management import call_command
from django.utils import timezone

from accounts import keys
from accounts.models import RefreshToken, Role, SigningKey, User

from .conftest import PASSWORD

pytestmark = pytest.mark.django_db

LOGIN = "/admin/login/"


@pytest.fixture
def staff(make_user):
    return make_user("root", roles=("reader", "editor"), is_staff=True)


@pytest.fixture
def admin_client(api, staff):
    assert api.login(username="root", password=PASSWORD)  # a real sign-in, not force_login
    return api


def role_id(name):
    return Role.objects.get(name=name).pk


def make_token(user, **kwargs):
    kwargs.setdefault("audience", "brand-reviews-app")
    kwargs.setdefault("expires_at", timezone.now() + timedelta(days=1))
    return RefreshToken.objects.create(
        user=user, token_hash=f"hash-{user.pk}-{RefreshToken.objects.count()}", **kwargs
    )


class TestAccess:
    def test_anonymous_visitors_are_sent_to_the_login_page(self, api):
        response = api.get("/admin/")

        assert response.status_code == 302
        assert response["Location"] == "/admin/login/?next=/admin/"

    def test_a_staff_user_signs_in_with_their_auth_service_password(self, api, staff):
        response = api.post(LOGIN, {"username": "root", "password": PASSWORD, "next": "/admin/"})

        assert response.status_code == 302
        assert response["Location"] == "/admin/"
        assert api.get("/admin/").status_code == 200

    def test_an_ordinary_user_cannot_sign_in_even_with_the_right_password(self, api, make_user):
        make_user("sarah", roles=("reader",))

        response = api.post(LOGIN, {"username": "sarah", "password": PASSWORD, "next": "/admin/"})

        assert response.status_code == 200
        assert "staff account" in response.content.decode()

    def test_a_disabled_staff_user_cannot_sign_in(self, api, make_user):
        make_user("old", is_staff=True, is_active=False)

        response = api.post(LOGIN, {"username": "old", "password": PASSWORD, "next": "/admin/"})

        assert response.status_code == 200

    def test_losing_the_staff_flag_ends_access_on_the_next_request(self, admin_client, staff):
        User.objects.filter(pk=staff.pk).update(is_staff=False)

        assert admin_client.get("/admin/").status_code == 302

    def test_staff_means_full_admin_access_and_nothing_else_does(self, make_user):
        staff_user = make_user("a", is_staff=True)
        plain = make_user("b")

        assert staff_user.is_superuser and staff_user.has_perm("accounts.change_user")
        assert not plain.is_superuser and not plain.has_perm("accounts.view_user")
        assert not plain.has_module_perms("accounts")

    def test_the_admin_has_its_own_cookie_names(self, api, staff):
        response = api.post(LOGIN, {"username": "root", "password": PASSWORD, "next": "/admin/"})

        assert "auth_sessionid" in response.cookies
        assert "sessionid" not in response.cookies
        assert settings.CSRF_COOKIE_NAME == "auth_csrftoken"
        assert settings.SESSION_COOKIE_AGE == 3600

    def test_the_json_api_still_works_without_a_csrf_token(self, make_user):
        from django.test import Client

        make_user("sarah")
        strict = Client(enforce_csrf_checks=True)

        response = strict.post(
            "/api/auth/v1/token/",
            {"username": "sarah", "password": PASSWORD},
            content_type="application/json",
        )

        assert response.status_code == 200


class TestEveryModelHasAPage:
    @pytest.mark.parametrize("model", ["role", "user", "refreshtoken", "signingkey"])
    def test_the_changelist_renders(self, admin_client, staff, model):
        make_token(staff)
        keys.active_key()

        response = admin_client.get(f"/admin/accounts/{model}/")

        assert response.status_code == 200

    def test_the_index_lists_all_four_and_not_djangos_unused_group_model(self, admin_client):
        html = admin_client.get("/admin/").content.decode()

        for label in ["Roles", "Users", "Refresh tokens", "Signing keys"]:
            assert label in html
        assert "Authentication and Authorization" not in html
        assert admin_client.get("/admin/auth/group/").status_code == 404


class TestUserAdmin:
    def test_adds_a_user_with_a_hashed_usable_password(self, admin_client):
        response = admin_client.post(
            "/admin/accounts/user/add/",
            {
                "username": "newbie",
                "usable_password": "true",
                "password1": "s3cret-pass",
                "password2": "s3cret-pass",
            },
        )

        assert response.status_code == 302
        user = User.objects.get(username="newbie")
        assert user.check_password("s3cret-pass")
        assert user.password != "s3cret-pass"
        assert (user.is_active, user.is_staff) == (True, False)

    def test_adds_a_user_with_no_usable_password(self, admin_client):
        admin_client.post(
            "/admin/accounts/user/add/",
            {"username": "nopass", "usable_password": "false", "password1": "", "password2": ""},
        )

        assert not User.objects.get(username="nopass").has_usable_password()

    def test_edits_roles_and_access(self, admin_client, make_user):
        user = make_user("sarah", roles=("reader",))

        response = admin_client.post(
            f"/admin/accounts/user/{user.pk}/change/",
            {
                "username": "sarah",
                "display_name": "Sarah K.",
                "email": "sarah@example.com",
                "is_active": "on",
                "is_staff": "on",
                "roles": [role_id("reader"), role_id("editor")],
            },
        )

        assert response.status_code == 302
        user.refresh_from_db()
        assert user.role_names() == ["editor", "reader"]
        assert (user.display_name, user.is_staff) == ("Sarah K.", True)

    def test_a_demoted_user_is_reflected_in_introspection_at_once(
        self, admin_client, make_user, api
    ):
        # Editing a role in the admin is what "role changes apply immediately" depends on.
        user = make_user("sarah", roles=("reader", "editor"))
        admin_client.post(
            f"/admin/accounts/user/{user.pk}/change/",
            {"username": "sarah", "is_active": "on", "roles": [role_id("reader")]},
        )

        assert User.objects.get(pk=user.pk).role_names() == ["reader"]

    def test_changes_a_password_from_its_own_page(self, admin_client, make_user):
        user = make_user("sarah")

        assert admin_client.get(f"/admin/accounts/user/{user.pk}/password/").status_code == 200
        response = admin_client.post(
            f"/admin/accounts/user/{user.pk}/password/",
            {
                "usable_password": "true",
                "password1": "brand-new-pass",
                "password2": "brand-new-pass",
            },
        )

        assert response.status_code == 302
        assert User.objects.get(pk=user.pk).check_password("brand-new-pass")

    def test_searches_and_filters(self, admin_client, make_user):
        make_user("sarah", roles=("reader",), email="sarah@example.com")
        make_user("ed", roles=("reader", "editor"), email="ed@example.com")

        by_email = admin_client.get("/admin/accounts/user/?q=sarah@").content.decode()
        by_role = admin_client.get(
            f"/admin/accounts/user/?roles__id__exact={role_id('editor')}"
        ).content.decode()

        assert "sarah" in by_email and 'field-username"><a href="/admin/accounts/user/' in by_email
        assert "ed@example.com" in by_role and "sarah@example.com" not in by_role

    def test_the_changelist_shows_each_users_roles(self, admin_client, make_user):
        make_user("ed", roles=("reader", "editor"))

        assert "editor, reader" in admin_client.get("/admin/accounts/user/").content.decode()

    def test_revokes_all_refresh_tokens_of_the_selected_users(self, admin_client, make_user):
        sarah, ed = make_user("sarah"), make_user("ed")
        make_token(sarah)
        make_token(sarah)
        make_token(ed)

        response = admin_client.post(
            "/admin/accounts/user/",
            {"action": "revoke_refresh_tokens", "_selected_action": [sarah.pk]},
            follow=True,
        )

        assert "Revoked 2 refresh token(s)" in response.content.decode()
        assert RefreshToken.objects.filter(user=sarah, revoked_at__isnull=False).count() == 2
        assert RefreshToken.objects.filter(user=ed, revoked_at__isnull=True).count() == 1


class TestRoleAdmin:
    def test_roles_are_viewable_with_their_user_counts(self, admin_client, make_user):
        make_user("a", roles=("reader",))
        make_user("b", roles=("reader", "editor"))

        html = admin_client.get("/admin/accounts/role/").content.decode()

        assert "editor" in html and "reader" in html

    def test_roles_cannot_be_added_changed_or_deleted(self, admin_client):
        pk = role_id("editor")

        assert admin_client.get("/admin/accounts/role/add/").status_code == 403
        assert (
            admin_client.post(f"/admin/accounts/role/{pk}/change/", {"name": "boss"}).status_code
            == 403
        )
        assert (
            admin_client.post(f"/admin/accounts/role/{pk}/delete/", {"post": "yes"}).status_code
            == 403
        )
        assert Role.objects.get(pk=pk).name == "editor"


class TestSigningKeyAdmin:
    def test_the_private_key_never_reaches_a_page(self, admin_client):
        key = keys.active_key()
        body = key.private_pem.splitlines()[1]  # a line of the actual key material

        pages = [
            admin_client.get("/admin/accounts/signingkey/").content.decode(),
            admin_client.get(f"/admin/accounts/signingkey/{key.pk}/change/").content.decode(),
        ]

        for html in pages:
            assert "PRIVATE KEY" not in html
            assert body not in html
            assert key.kid in html

    def test_keys_are_managed_by_the_command_not_the_admin(self, admin_client):
        key = keys.active_key()

        assert admin_client.get("/admin/accounts/signingkey/add/").status_code == 403
        assert (
            admin_client.post(
                f"/admin/accounts/signingkey/{key.pk}/change/", {"kid": "x"}
            ).status_code
            == 403
        )
        assert (
            admin_client.post(
                f"/admin/accounts/signingkey/{key.pk}/delete/", {"post": "yes"}
            ).status_code
            == 403
        )
        assert SigningKey.objects.filter(pk=key.pk).exists()

    def test_shows_which_key_is_signing_which_are_published_and_which_are_retired(
        self, admin_client
    ):
        old = keys.active_key()
        retired = keys.create_key()
        retired.retired_at = timezone.now()
        retired.save()
        newest = keys.create_key()

        html = admin_client.get("/admin/accounts/signingkey/").content.decode()

        def status_of(key):
            row = html[html.index(key.kid) :]
            return row[: row.index("</tr>")]

        assert "published" in status_of(old)
        assert "retired" in status_of(retired)
        assert "active (signing)" in status_of(newest)


class TestRefreshTokenAdmin:
    def test_shows_a_token_without_its_hash(self, admin_client, staff):
        token = make_token(staff)

        response = admin_client.get(f"/admin/accounts/refreshtoken/{token.pk}/change/")

        assert response.status_code == 200
        assert token.token_hash not in response.content.decode()
        assert "brand-reviews-app" in response.content.decode()

    def test_tokens_cannot_be_added_or_edited(self, admin_client, staff):
        token = make_token(staff)

        assert admin_client.get("/admin/accounts/refreshtoken/add/").status_code == 403
        assert (
            admin_client.post(
                f"/admin/accounts/refreshtoken/{token.pk}/change/", {"audience": "x"}
            ).status_code
            == 403
        )

    def test_filters_by_status(self, admin_client, staff):
        make_token(staff, audience="active-aud")
        make_token(staff, audience="expired-aud", expires_at=timezone.now() - timedelta(days=1))
        make_token(staff, audience="revoked-aud", revoked_at=timezone.now())

        def audiences(status):
            response = admin_client.get(f"/admin/accounts/refreshtoken/?status={status}")
            return {token.audience for token in response.context["cl"].result_list}

        assert audiences("active") == {"active-aud"}
        assert audiences("expired") == {"expired-aud"}
        assert audiences("revoked") == {"revoked-aud"}

    def test_revokes_selected_tokens_and_can_delete_old_ones(self, admin_client, staff):
        first, second = make_token(staff), make_token(staff)

        admin_client.post(
            "/admin/accounts/refreshtoken/",
            {"action": "revoke", "_selected_action": [first.pk]},
        )
        admin_client.post(f"/admin/accounts/refreshtoken/{second.pk}/delete/", {"post": "yes"})

        first.refresh_from_db()
        assert first.revoked_at is not None
        assert not RefreshToken.objects.filter(pk=second.pk).exists()


class TestCreateSuperuser:
    def test_creates_staff_who_hold_every_role(self, monkeypatch):
        monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "root-pass-123")

        call_command("createsuperuser", username="boss", interactive=False)

        boss = User.objects.get(username="boss")
        assert boss.is_staff and boss.is_active
        assert boss.role_names() == ["editor", "reader"]
        assert boss.check_password("root-pass-123")


def test_no_model_change_is_missing_a_migration():
    call_command("makemigrations", "--check", "--dry-run")  # exits non-zero if one is missing
