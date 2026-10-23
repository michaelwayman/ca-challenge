"""Runs the importer against the real WordPress data in the wp-db container.

Start it with `make wp-source`; the tests skip when it is not reachable.
"""

from decimal import Decimal

import pymysql
import pytest

from catalog.management.commands.import_wordpress import Importer
from catalog.models import Brand, Industry, Review, Reviewer
from shared.wp_migration.source import MariaDBSource, connection_settings

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def source():
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
    return MariaDBSource(**config)


def test_imports_the_seeded_site(source):
    Importer(source).run()

    assert Industry.objects.count() == 5
    assert Brand.objects.count() == 5
    assert Review.objects.count() == 60
    assert Reviewer.objects.count() == 8
    assert all(b.reviews.count() == 12 for b in Brand.objects.all())
    assert all(b.industries.count() == 1 for b in Brand.objects.all())
    assert not Review.objects.filter(reviewer__isnull=True).exists()


def test_rerun_is_a_no_op(source):
    Importer(source).run()

    report = Importer(source).run()

    assert all(c.created == c.updated == 0 for c in report.counts.values())
    assert Review.objects.count() == 60


def test_the_rating_is_derived_from_the_reviews_not_wordpress_stored_average(source):
    # WordPress stores 3.9 for HomeShield Pro; its 12 reviews average 3.08.
    Importer(source).run()

    homeshield = Brand.objects.with_stats().get(slug="homeshield-pro")

    assert homeshield.average_rating == Decimal("3.1")
    assert homeshield.review_count == 12


def test_api_serves_the_imported_site(source, client):
    Importer(source).run()

    data = client.get("/api/brands/", {"ordering": "-average_rating"}).json()

    assert data["count"] == 5
    # Derived averages, not the stored ACF values (which would rank urbanretail first).
    assert [(r["slug"], r["average_rating"]) for r in data["results"]] == [
        ("acme-insurance", 3.9),
        ("primepath-bank", 3.8),
        ("urbanretail-co", 3.7),
        ("swiftstream-internet", 3.5),
        ("homeshield-pro", 3.1),
    ]
    assert all(r["review_count"] == 12 for r in data["results"])
    for row in data["results"]:
        best = max(
            Brand.objects.get(slug=row["slug"]).reviews.all(),
            key=lambda r: (r.rating, r.published_at, r.id),
        )
        assert row["top_review"]["slug"] == best.slug
