from collections.abc import Mapping

from rest_framework import serializers

from catalog.models import Brand, Industry, Review
from catalog.sanitize import sanitize_html
from catalog.text import excerpt, plain_text, snippet


class IndustrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Industry
        fields = ["name", "slug"]


class TopReviewSerializer(serializers.ModelSerializer):
    snippet = serializers.SerializerMethodField()
    reviewer = serializers.SerializerMethodField()
    url = serializers.CharField(source="get_absolute_url")

    class Meta:
        model = Review
        fields = ["slug", "title", "rating", "snippet", "reviewer", "url"]

    def get_snippet(self, review) -> str:
        return snippet(review.body)

    def get_reviewer(self, review) -> str | None:
        return review.reviewer.display_name if review.reviewer else None


class BrandListSerializer(serializers.ModelSerializer):
    industries = IndustrySerializer(many=True, read_only=True)
    average_rating = serializers.FloatField(read_only=True, allow_null=True)
    review_count = serializers.IntegerField(read_only=True)
    excerpt = serializers.SerializerMethodField()
    top_review = serializers.SerializerMethodField()
    url = serializers.CharField(source="get_absolute_url")

    class Meta:
        model = Brand
        fields = [
            "name",
            "slug",
            "url",
            "industries",
            "average_rating",
            "review_count",
            "excerpt",
            "top_review",
        ]

    def get_excerpt(self, brand) -> str:
        # Plain text, for the cards: clients must show it as text, never as HTML.
        return excerpt(brand.description)

    def get_top_review(self, brand):
        # Prefetched by the view as a list of at most one review.
        top = brand.top_reviews
        return TopReviewSerializer(top[0]).data if top else None


class BrandDetailSerializer(BrandListSerializer):
    """The list row plus the full description, which is sanitized HTML."""

    class Meta(BrandListSerializer.Meta):
        fields = [*BrandListSerializer.Meta.fields, "description"]


class BrandUpdateSerializer(serializers.ModelSerializer):
    """What an editor may change. Anything else in the body is an error rather than being
    silently ignored, so a client that thinks it edited the name finds out."""

    # HTML, cleaned down to the same allowlist as every other write path (the model cleans it
    # again on save). The limit applies to what was sent, before cleaning.
    description = serializers.CharField(max_length=20_000, trim_whitespace=True)

    class Meta:
        model = Brand
        fields = ["description"]

    def validate_description(self, value: str) -> str:
        cleaned = sanitize_html(value)
        if not plain_text(cleaned):
            raise serializers.ValidationError("Nothing is left once unsafe markup is removed.")
        return cleaned

    def to_internal_value(self, data):
        if not isinstance(data, Mapping):
            return super().to_internal_value(data)  # DRF's own "Invalid data" 400
        unknown = sorted(set(data) - set(self.fields))
        if unknown:
            message = "This field cannot be edited."
            raise serializers.ValidationError(dict.fromkeys(unknown, message))
        # DRF's CharField would quietly turn the number 5 into "5".
        if "description" in data and not isinstance(data["description"], str):
            raise serializers.ValidationError({"description": "Not a valid string."})
        return super().to_internal_value(data)
