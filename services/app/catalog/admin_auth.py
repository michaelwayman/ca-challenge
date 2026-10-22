"""Sign-in for the admin site, delegated to the auth service.

The main app stores no passwords. A person types their auth-service username and password
into the admin login form; this backend checks them with the auth service (catalog.auth.login)
and lets in only editors. Django still needs a local user row to hang a session and the change
history on, so one is kept per person: keyed by their auth-service id, with an unusable
password, holding nothing but a staff flag that is re-derived from the auth service at every
sign-in. Revoking someone's editor role therefore takes effect at their next sign-in attempt
(the row is demoted at once), and an existing session lasts at most SESSION_COOKIE_AGE.
"""

from django.contrib.auth import get_user_model

from ca_authlib.claims import Role

from . import auth


class AuthServiceBackend:
    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None
        claims = auth.login(username, password)
        if claims is None:
            return None  # wrong password, or nothing certain: never demote on a failed check
        is_editor = claims.has_role(Role.EDITOR)
        user_model = get_user_model()
        user = user_model.objects.filter(username=claims.sub).first()
        if not is_editor:
            if user is not None:  # a former editor: cut off any session they still hold
                user.is_staff = user.is_superuser = False
                user.save(update_fields=["is_staff", "is_superuser"])
            return None
        if user is None:
            user = user_model(username=claims.sub)
            user.set_unusable_password()
        user.first_name = username[:150]  # what the admin shows; the username key is the stable id
        user.is_active = True
        user.is_staff = user.is_superuser = True
        user.save()
        return user

    def get_user(self, user_id):
        user = get_user_model().objects.filter(pk=user_id).first()
        return user if user is not None and user.is_active else None
