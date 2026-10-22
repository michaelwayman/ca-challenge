from datetime import datetime

from ca_authlib.ids import user_id_from_wp_id  # noqa: F401  (re-exported for tests)
from catalog.management.commands.wp_migration.source import WPPost, WPTerm, WPUser


class FakeSource:
    def __init__(
        self, industries=(), brands=(), reviews=(), users=(), links=None, pages=(), front_page=None
    ):
        self._industries = list(industries)
        self._brands = list(brands)
        self._reviews = list(reviews)
        self._users = list(users)
        self._links = links or {}
        self._pages = list(pages)
        self._front_page = front_page

    def industries(self):
        return list(self._industries)

    def brands(self):
        return list(self._brands)

    def reviews(self):
        return list(self._reviews)

    def pages(self):
        return list(self._pages)

    def front_page_id(self):
        return self._front_page

    def users(self):
        return list(self._users)

    def brand_industries(self):
        return dict(self._links)


def term(wp_id=2, name="Insurance", slug="insurance"):
    return WPTerm(wp_id, name, slug)


def user(wp_id=2, display_name="Sarah K."):
    return WPUser(wp_id, display_name)


def brand_post(wp_id=7, slug="acme", title="Acme", content="<p>" + "word " * 40 + "</p>", **meta):
    meta = {
        "website_url": "https://acme.example.com",
        "founded_year": "1985",
        "headquarters": "Hartford, CT",
        "_yoast_wpseo_title": "Acme reviews",
        "_yoast_wpseo_metadesc": "Read about Acme",
        **meta,
    }
    return WPPost(wp_id, slug, title, content, datetime(2026, 5, 19, 20, 29), 0, meta)


def review_post(wp_id=12, slug="great", title="Great", content="<p>Nice</p>", author=2, **meta):
    meta = {
        "rating": "5",
        "reviewer_name": "Sarah K.",
        "reviewer_location": "Albany, NY",
        "brand": "7",
        **meta,
    }
    return WPPost(wp_id, slug, title, content, datetime(2026, 5, 19, 20, 29, 13), author, meta)


def page_post(wp_id=5, slug="about", title="About", content="<p>About us</p>", parent_id=0):
    return WPPost(wp_id, slug, title, content, datetime(2026, 5, 19, 20, 29, 1), 0, {}, parent_id)


def standard_source(**overrides):
    parts = {
        "industries": [term()],
        "brands": [brand_post()],
        "reviews": [review_post()],
        "users": [user()],
        "links": {7: [2]},
    }
    return FakeSource(**{**parts, **overrides})
