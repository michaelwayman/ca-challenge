import pymysql
import pytest

from shared.wp_migration.source import MariaDBSource, connection_settings, parse_capabilities


class TestParseCapabilities:
    @pytest.mark.parametrize(
        ("serialized", "expected"),
        [
            ('a:1:{s:13:"administrator";b:1;}', ("administrator",)),
            ('a:2:{s:6:"editor";b:1;s:6:"author";b:1;}', ("editor", "author")),
            ('a:2:{s:6:"editor";b:0;s:10:"subscriber";b:1;}', ("subscriber",)),
            ("a:0:{}", ()),
            ("", ()),
        ],
    )
    def test_reads_the_granted_roles(self, serialized, expected):
        assert parse_capabilities(serialized) == expected


class TestConnectionSettings:
    def test_reads_the_environment(self, monkeypatch):
        monkeypatch.setenv("WP_DB_HOST", "wp-db")
        monkeypatch.setenv("WP_DB_PORT", "3306")
        monkeypatch.setenv("WP_TABLE_PREFIX", "site2_")

        config = connection_settings()

        assert (config["host"], config["port"], config["table_prefix"]) == ("wp-db", 3306, "site2_")

    def test_defaults_to_the_host_side_port(self, monkeypatch):
        for name in ("WP_DB_HOST", "WP_DB_PORT", "WP_TABLE_PREFIX"):
            monkeypatch.delenv(name, raising=False)

        config = connection_settings()

        assert (config["host"], config["port"], config["table_prefix"]) == (
            "127.0.0.1",
            3307,
            "wp_",
        )


@pytest.mark.parametrize("prefix", ["wp_; DROP TABLE x", "wp-", "`wp`"])
def test_a_table_prefix_that_could_inject_sql_is_refused(prefix):
    with pytest.raises(ValueError, match="invalid table prefix"):
        MariaDBSource(host="h", port=1, user="u", password="p", database="d", table_prefix=prefix)


@pytest.mark.integration
def test_reads_the_seeded_wordpress_site():
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
    source = MariaDBSource(**config)

    users = {u.login: u for u in source.users()}

    assert len(source.industries()) == 5
    assert len(source.brands()) == 5
    assert len(source.reviews()) == 60
    assert len(users) == 9
    assert users["admin"].roles == ("administrator",)
    assert users["admin"].password_hash.startswith("$wp$2y$")
    assert "password_hash" not in repr(users["admin"])
    assert (users["sarah_k"].display_name, users["sarah_k"].email) == (
        "Sarah K.",
        "sarah@example.com",
    )
