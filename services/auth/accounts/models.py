import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models


class Role(models.Model):
    name = models.CharField(max_length=32, unique=True)

    def __str__(self):
        return self.name


class UserManager(BaseUserManager):
    def create_user(self, username, password=None, **extra):
        user = self.model(username=username, **extra)
        user.set_password(password)  # None gives an unusable password
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra):
        """Used by `createsuperuser`: staff, and a holder of every role, so the account
        can sign in to the admin and also use the APIs."""
        user = self.create_user(username, password, is_staff=True, **extra)
        user.roles.set(Role.objects.all())
        return user


class User(AbstractBaseUser):
    """The identity of record. The main app keeps only this id, never credentials."""

    # Users migrated from WordPress get uuid5 of their WordPress id (shared.wp_migration.ids), so
    # a re-import finds them again and the main app can compute the same id; everyone else gets a
    # random uuid4.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(blank=True)
    display_name = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False, help_text="May sign in to this admin site.")
    roles = models.ManyToManyField(Role, related_name="users", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "username"
    objects = UserManager()

    def __str__(self):
        return self.username

    # Django's admin asks for these. There is one level of admin access here: staff.
    @property
    def is_superuser(self) -> bool:
        return self.is_staff

    def has_perm(self, perm, obj=None) -> bool:
        return self.is_active and self.is_staff

    def has_module_perms(self, app_label) -> bool:
        return self.is_active and self.is_staff

    def role_names(self) -> list[str]:
        return sorted(self.roles.values_list("name", flat=True))


class RefreshToken(models.Model):
    """Opaque and single-use: only a hash is stored, and using it rotates it."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="refresh_tokens")
    token_hash = models.CharField(max_length=64, unique=True)
    audience = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["expires_at"], name="refresh_token_expires_idx")]

    def __str__(self):
        return f"refresh token for {self.user_id}"


class SigningKey(models.Model):
    """Ed25519 key pair. The newest unretired key signs; every unretired key is
    published, so tokens signed by an older key stay valid until it is retired.

    The private key is stored in the database unencrypted. That is a dev-grade choice;
    in production it would live in a KMS or secrets manager.
    """

    kid = models.CharField(max_length=64, unique=True)
    private_pem = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    retired_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.kid
