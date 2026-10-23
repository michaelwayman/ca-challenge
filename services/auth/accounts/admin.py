from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group
from django.db.models import Count, Exists, OuterRef, Q
from django.utils import timezone

from .models import RefreshToken, Role, SigningKey, User

admin.site.site_header = "Brand Reviews auth admin"
admin.site.site_title = "Auth admin"
admin.site.index_title = "Users, roles and tokens"

# Django's own Group model is not used here: roles (see Role) are the mechanism.
if admin.site.is_registered(Group):
    admin.site.unregister(Group)


class ReadOnlyAdmin(admin.ModelAdmin):
    """Records that are managed by code, not by hand: viewable, never added or edited."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Role)
class RoleAdmin(ReadOnlyAdmin):
    """The roles are a fixed set the shared library defines (shared.auth.claims.Role), so
    they cannot be added, renamed or removed here; assign them to users instead."""

    list_display = ("name", "user_count")
    fields = ("name",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_user_count=Count("users"))

    @admin.display(ordering="_user_count", description="Users")
    def user_count(self, obj):
        return obj._user_count


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("username",)
    list_display = ("username", "email", "display_name", "role_list", "is_active", "is_staff")
    list_filter = ("is_active", "is_staff", "roles")
    search_fields = ("username", "email", "display_name")
    filter_horizontal = ("roles",)
    readonly_fields = ("id", "last_login", "created_at")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Profile", {"fields": ("display_name", "email")}),
        ("Access", {"fields": ("is_active", "is_staff", "roles")}),
        ("History", {"fields": ("id", "last_login", "created_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "usable_password", "password1", "password2"),
            },
        ),
    )
    actions = ["revoke_refresh_tokens"]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("roles")

    @admin.display(description="Roles")
    def role_list(self, obj):
        return ", ".join(sorted(role.name for role in obj.roles.all())) or "none"

    @admin.action(description="Revoke all refresh tokens of the selected users")
    def revoke_refresh_tokens(self, request, queryset):
        revoked = RefreshToken.objects.filter(user__in=queryset, revoked_at__isnull=True).update(
            revoked_at=timezone.now()
        )
        self.message_user(
            request,
            f"Revoked {revoked} refresh token(s). Access tokens already issued stay valid until "
            "they expire (up to 10 minutes).",
        )


class TokenStatusFilter(admin.SimpleListFilter):
    title = "status"
    parameter_name = "status"

    def lookups(self, request, model_admin):
        return [("active", "Active"), ("expired", "Expired"), ("revoked", "Revoked")]

    def queryset(self, request, queryset):
        now = timezone.now()
        match self.value():
            case "active":
                return queryset.filter(revoked_at__isnull=True, expires_at__gt=now)
            case "expired":
                return queryset.filter(revoked_at__isnull=True, expires_at__lte=now)
            case "revoked":
                return queryset.filter(revoked_at__isnull=False)
        return queryset


@admin.register(RefreshToken)
class RefreshTokenAdmin(ReadOnlyAdmin):
    """The token itself is stored only as a hash and is never shown."""

    list_display = ("user", "audience", "created_at", "expires_at", "status")
    list_filter = (TokenStatusFilter, "audience")
    list_select_related = ("user",)
    search_fields = ("user__username",)
    date_hierarchy = "created_at"
    fields = ("user", "audience", "created_at", "expires_at", "revoked_at")
    readonly_fields = fields
    actions = ["revoke"]

    def has_delete_permission(self, request, obj=None):
        return True  # clearing out old rows is fine; creating or editing them is not

    @admin.display(description="Status")
    def status(self, obj):
        if obj.revoked_at is not None:
            return "revoked"
        return "expired" if obj.expires_at <= timezone.now() else "active"

    @admin.action(description="Revoke the selected refresh tokens")
    def revoke(self, request, queryset):
        revoked = queryset.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())
        self.message_user(request, f"Revoked {revoked} refresh token(s).")


@admin.register(SigningKey)
class SigningKeyAdmin(ReadOnlyAdmin):
    """Rotate keys with `manage.py rotate_signing_key`. The private key is never shown."""

    list_display = ("kid", "created_at", "status", "retired_at")
    fields = ("kid", "created_at", "retired_at")
    readonly_fields = fields
    ordering = ("-created_at", "-id")

    def get_queryset(self, request):
        newer_unretired = SigningKey.objects.filter(retired_at__isnull=True).filter(
            Q(created_at__gt=OuterRef("created_at"))
            | Q(created_at=OuterRef("created_at"), id__gt=OuterRef("id"))
        )
        return super().get_queryset(request).annotate(_superseded=Exists(newer_unretired))

    @admin.display(description="Status")
    def status(self, obj):
        if obj.retired_at is not None:
            return "retired"
        return "published" if obj._superseded else "active (signing)"
