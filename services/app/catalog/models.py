from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg, Count, Q
from django.db.models.functions import Round
from django.urls import reverse

from .sanitize import sanitize_html

# Every model below starts with the same three fields. wp_id is the WordPress importer's
# re-run key: unique, and NULL for rows created natively (Postgres allows many NULLs under
# UNIQUE). created_at and updated_at are the usual timestamps.


class Industry(models.Model):
    wp_id = models.PositiveIntegerField(unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "industries"

    def __str__(self):
        return self.name


class BrandQuerySet(models.QuerySet):
    def with_stats(self):
        """Annotate average_rating (1 dp, NULL when unreviewed) and review_count."""
        return self.annotate(
            average_rating=Round(
                Avg(
                    "reviews__rating",
                    output_field=models.DecimalField(max_digits=3, decimal_places=1),
                ),
                1,
            ),
            review_count=Count("reviews"),
        )


class Brand(models.Model):
    wp_id = models.PositiveIntegerField(unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    slug = models.SlugField(max_length=200, unique=True)
    name = models.CharField(max_length=200)
    # Sanitized HTML (save() cleans it). The brand page renders it as HTML; the cards show only
    # a plain-text excerpt of it, always escaped.
    description = models.TextField(blank=True)
    website_url = models.URLField(blank=True)
    founded_year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1800), MaxValueValidator(2100)],
    )
    headquarters = models.CharField(max_length=200, blank=True)
    industries = models.ManyToManyField(Industry, related_name="brands", blank=True)
    seo = models.JSONField(default=dict, blank=True)
    # What the importer last read from WordPress. While `description` still equals it, nobody has
    # edited the text here, so the next import may replace it; once they differ, the edit is kept.
    wp_description = models.TextField(blank=True, editable=False)

    objects = BrandQuerySet.as_manager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.description = sanitize_html(self.description)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("brand-detail", kwargs={"slug": self.slug})


class Reviewer(models.Model):
    wp_id = models.PositiveIntegerField(unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    display_name = models.CharField(max_length=100)
    auth_user_id = models.UUIDField(null=True, blank=True, unique=True)

    def __str__(self):
        return self.display_name


class Review(models.Model):
    wp_id = models.PositiveIntegerField(unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    slug = models.SlugField(max_length=200, unique=True)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    rating = models.PositiveSmallIntegerField()
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE, related_name="reviews")
    reviewer = models.ForeignKey(
        Reviewer, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviews"
    )
    reviewer_location = models.CharField(max_length=100, blank=True)
    published_at = models.DateTimeField()

    class Meta:
        ordering = ["-published_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(rating__gte=1, rating__lte=5), name="review_rating_1_to_5"
            ),
        ]
        indexes = [models.Index(fields=["brand", "-published_at"], name="review_brand_pub_idx")]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        self.body = sanitize_html(self.body)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("review-detail", kwargs={"slug": self.slug})


# Top-level routes a static page must not shadow (see config/urls.py and catalog/urls.py).
RESERVED_PAGE_SLUGS = frozenset({"admin", "api", "brand", "healthz", "review", "static"})


class Page(models.Model):
    """A static page (About, Contact, ...), served at /<slug>/ like WordPress does."""

    wp_id = models.PositiveIntegerField(unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    slug = models.SlugField(max_length=200, unique=True)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)  # sanitized HTML (save() cleans it)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        self.body = sanitize_html(self.body)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("page-detail", kwargs={"slug": self.slug})
