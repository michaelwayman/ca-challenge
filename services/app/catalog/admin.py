from django import forms
from django.contrib import admin
from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.db.models import Count

from .models import RESERVED_PAGE_SLUGS, Brand, Industry, Page, Review, Reviewer

admin.site.site_header = "Brand Reviews admin"
admin.site.site_title = "Brand Reviews admin"
admin.site.index_title = "Content"

# Staff sign in through the auth service (see admin_auth.py), so Django's own user and group
# admin, which would manage local passwords and permissions, is switched off.
for model in (User, Group):
    if admin.site.is_registered(model):
        admin.site.unregister(model)

IMPORT_NOTE = (
    "Filled in by import_wordpress. Running it again puts WordPress's values back over any "
    "edits to imported fields (a brand's description is the one exception: an edited "
    "description is kept)."
)
TIMESTAMPS = ("created_at", "updated_at")


class BrandForm(forms.ModelForm):
    # A URL typed without a scheme ("example.com") becomes https, which is also Django 6's default.
    website_url = forms.URLField(required=False, assume_scheme="https")

    class Meta:
        model = Brand
        fields = (
            "name",
            "slug",
            "industries",
            "description",
            "website_url",
            "founded_year",
            "headquarters",
            "seo",
        )


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = (
            "title",
            "slug",
            "brand",
            "reviewer",
            "rating",
            "published_at",
            "body",
            "reviewer_location",
        )


class PageForm(forms.ModelForm):
    class Meta:
        model = Page
        fields = ("title", "slug", "body")

    def clean_slug(self):
        slug = self.cleaned_data["slug"]
        if slug in RESERVED_PAGE_SLUGS:
            raise ValidationError(f'"{slug}" is a route of the site; choose another slug.')
        return slug


@admin.register(Industry)
class IndustryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "brand_count", "wp_id")
    ordering = ("name",)  # explicit: an aggregating queryset ignores Meta.ordering
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("wp_id", *TIMESTAMPS)
    fieldsets = (
        (None, {"fields": ("name", "slug")}),
        ("Import", {"fields": ("wp_id", *TIMESTAMPS), "description": IMPORT_NOTE}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_brand_count=Count("brands"))

    @admin.display(ordering="_brand_count", description="Brands")
    def brand_count(self, obj):
        return obj._brand_count


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    form = BrandForm
    list_display = ("name", "slug", "industry_names", "avg_rating", "reviews", "headquarters")
    list_filter = ("industries",)
    ordering = ("name",)
    search_fields = ("name", "slug", "headquarters")
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ("industries",)
    readonly_fields = ("wp_id", *TIMESTAMPS)
    fieldsets = (
        (None, {"fields": ("name", "slug", "industries")}),
        ("Content", {"fields": ("description",)}),
        ("Facts", {"fields": ("website_url", "founded_year", "headquarters")}),
        ("SEO", {"fields": ("seo",), "classes": ("collapse",)}),
        (
            "Import",
            {
                "fields": ("wp_id", *TIMESTAMPS),
                "classes": ("collapse",),
                "description": IMPORT_NOTE
                + " The imported average rating is kept for audit; the site shows the rating "
                "derived from the reviews.",
            },
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).with_stats().prefetch_related("industries")

    @admin.display(description="Industries")
    def industry_names(self, obj):
        return ", ".join(sorted(industry.name for industry in obj.industries.all())) or "none"

    @admin.display(ordering="average_rating", description="Rating")
    def avg_rating(self, obj):
        return "none yet" if obj.average_rating is None else obj.average_rating

    @admin.display(ordering="review_count", description="Reviews")
    def reviews(self, obj):
        return obj.review_count


@admin.register(Reviewer)
class ReviewerAdmin(admin.ModelAdmin):
    list_display = ("display_name", "review_count", "wp_id")
    ordering = ("display_name",)
    search_fields = ("display_name",)
    readonly_fields = ("auth_user_id", "wp_id", *TIMESTAMPS)
    fieldsets = (
        (None, {"fields": ("display_name",)}),
        (
            "Identity and import",
            {
                "fields": ("auth_user_id", "wp_id", *TIMESTAMPS),
                "description": "The auth-service user this reviewer is linked to is set by the "
                "importer and is not edited by hand. " + IMPORT_NOTE,
            },
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_review_count=Count("reviews"))

    @admin.display(ordering="_review_count", description="Reviews")
    def review_count(self, obj):
        return obj._review_count


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    form = ReviewForm
    list_display = ("title", "brand", "reviewer", "rating", "published_at")
    list_filter = ("rating", "brand", "published_at")
    list_select_related = ("brand", "reviewer")
    search_fields = ("title", "body", "brand__name", "reviewer__display_name")
    autocomplete_fields = ("brand", "reviewer")
    date_hierarchy = "published_at"
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("wp_id", *TIMESTAMPS)
    fieldsets = (
        (None, {"fields": ("title", "slug", "brand", "reviewer", "rating", "published_at")}),
        ("Review", {"fields": ("body", "reviewer_location")}),
        (
            "Import",
            {
                "fields": ("wp_id", *TIMESTAMPS),
                "classes": ("collapse",),
                "description": IMPORT_NOTE,
            },
        ),
    )


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    form = PageForm
    list_display = ("title", "slug", "wp_id")
    search_fields = ("title", "slug", "body")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("wp_id", *TIMESTAMPS)
    fieldsets = (
        (None, {"fields": ("title", "slug", "body")}),
        (
            "Import",
            {
                "fields": ("wp_id", *TIMESTAMPS),
                "classes": ("collapse",),
                "description": IMPORT_NOTE,
            },
        ),
    )
