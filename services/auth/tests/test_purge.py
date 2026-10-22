from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from accounts import keys, tokens
from accounts.models import RefreshToken, SigningKey

NOW = timezone.now()


@pytest.fixture
def user(make_user):
    return make_user()


def refresh_token(user, *, expires_in, revoked=False):
    return RefreshToken.objects.create(
        user=user,
        token_hash=f"{expires_in}-{revoked}",
        audience="app",
        expires_at=NOW + timedelta(seconds=expires_in),
        revoked_at=NOW if revoked else None,
    )


def signing_key(*, retired_ago=None):
    key = keys.create_key()
    if retired_ago is not None:
        key.retired_at = NOW - timedelta(seconds=retired_ago)
        key.save(update_fields=["retired_at"])
    return key


class TestRefreshTokens:
    def test_expired_tokens_are_deleted_whether_or_not_they_were_used(self, user):
        refresh_token(user, expires_in=-60)
        refresh_token(user, expires_in=-60, revoked=True)

        assert tokens.purge_refresh_tokens(now=NOW) == 2
        assert not RefreshToken.objects.exists()

    def test_live_and_revoked_but_unexpired_tokens_are_kept(self, user):
        live = refresh_token(user, expires_in=3600)
        used = refresh_token(user, expires_in=3600, revoked=True)

        assert tokens.purge_refresh_tokens(now=NOW) == 0
        assert set(RefreshToken.objects.all()) == {live, used}

    def test_a_dry_run_counts_but_deletes_nothing(self, user):
        refresh_token(user, expires_in=-60)

        assert tokens.purge_refresh_tokens(now=NOW, dry_run=True) == 1
        assert RefreshToken.objects.count() == 1


class TestSigningKeys:
    def window(self, settings):
        return settings.ACCESS_TOKEN_TTL + keys.JWKS_CACHE_SECONDS

    def test_a_key_retired_past_the_window_is_deleted(self, db, settings):
        old = signing_key(retired_ago=self.window(settings) + 1)

        assert keys.purge_retired_keys(now=NOW) == 1
        assert not SigningKey.objects.filter(pk=old.pk).exists()

    def test_active_and_recently_retired_keys_are_kept(self, db, settings):
        active = signing_key()
        recent = signing_key(retired_ago=self.window(settings) - 1)

        assert keys.purge_retired_keys(now=NOW) == 0
        assert set(SigningKey.objects.all()) == {active, recent}


def test_the_command_reports_and_honours_dry_run(user, settings):
    refresh_token(user, expires_in=-60)
    signing_key(retired_ago=settings.ACCESS_TOKEN_TTL + keys.JWKS_CACHE_SECONDS + 1)

    out = StringIO()
    call_command("purge_tokens", "--dry-run", stdout=out)
    assert out.getvalue().strip() == "Would delete 1 refresh token(s) and 1 signing key(s)."
    assert RefreshToken.objects.count() == SigningKey.objects.count() == 1

    out = StringIO()
    call_command("purge_tokens", stdout=out)
    assert out.getvalue().strip() == "Deleted 1 refresh token(s) and 1 signing key(s)."
    assert not RefreshToken.objects.exists() and not SigningKey.objects.exists()
