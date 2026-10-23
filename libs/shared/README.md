# shared

The code the main app and the auth service both use, in two submodules. Keep it small: a module belongs here only
if more than one service imports it.

- **`shared.auth`**: the two sides of a token, so they cannot drift apart.
- **`shared.wp_migration`**: reading the WordPress site both services migrate from.

## What is in it

| Module | What it does |
|---|---|
| `auth.claims` | The token contract: `Claims`, `Role`, `issue_claims`, `encode_claims` / `decode_claims`, the `Introspection` shape. Tokens carry a version (`v`), so a new format can roll out without a simultaneous deploy |
| `auth.verify` | `TokenVerifier` and `JWKSClient`: check a token's signature, issuer, audience, expiry and version against the auth service's public keys (cached; no network call per request) |
| `auth.drf` | Django REST framework adapter (needs the `drf` extra): `JWTAuthentication` and `require_role(...)` |
| `auth.errors` | The exceptions the other `auth` modules raise |
| `auth.testing` | `TestKey`, for signing tokens in tests (not for production use) |
| `wp_migration.source` | `MariaDBSource` (needs the `wp` extra): reads industries, brands, reviews and users (with their WordPress roles) from the WordPress database. Also the row dataclasses, the `WordPressSource` protocol and `connection_settings()` (`WP_DB_*`) |
| `wp_migration.ids` | `user_id_from_wp_id()`: the deterministic user id both importers derive from a WordPress id |

Each service's import command turns these rows into its own models:
- `services/app/catalog/management/commands/import_wordpress.py`
- `services/auth/accounts/management/commands/import_wordpress_users.py`

The library never touches a Django model.

## Use it

**In a Django REST service** (the main app does this): point it at the auth service's keys, then protect views.

```python
# settings.py
CA_AUTH = {
    "JWKS_URL": "http://auth:8001/.well-known/jwks.json",
    "ISSUER": "brand-reviews-auth",
    "AUDIENCE": "brand-reviews-app",
    "ACCEPTED_TOKEN_VERSIONS": [1],
}

# views.py
from shared.auth.claims import Role
from shared.auth.drf import JWTAuthentication, require_role


class EditBrand(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [require_role(Role.EDITOR)]  # fresh=True also asks auth for current roles
```

**Anywhere else:** verify a token by hand.

```python
from shared.auth.verify import JWKSClient, TokenVerifier, http_fetch

verifier = TokenVerifier(
    JWKSClient(http_fetch("http://auth:8001/.well-known/jwks.json")),
    issuer="brand-reviews-auth",
    audience="brand-reviews-app",
    accepted_versions=[1],
)
claims = verifier.verify(token)  # raises TokenError if it is not valid
claims.sub, claims.has_role("editor")
```

**Read WordPress:**

```python
from shared.wp_migration.source import MariaDBSource

source = MariaDBSource.from_env()  # WP_DB_HOST, WP_DB_PORT, ... (defaults reach `make wp-source`)
for user in source.users():
    user.login, user.display_name, user.roles  # e.g. ("admin", "admin", ("administrator",))
```

## Test it

No service is needed. The one integration test reads the real WordPress database, and skips when `make wp-source`
is not running.

```bash
uv run --package shared --group test pytest libs/shared
```

## Publish a tagged version

The version is in two places: `version` in `pyproject.toml` and `__version__` in `src/shared/__init__.py`.

```bash
# 1. Bump both, then run the tests (above).
# 2. Commit and tag. The tag is shared/vX.Y.Z, so the library can be released on its own.
git commit -am "shared 0.3.0"
git tag shared/v0.3.0
git push origin main shared/v0.3.0

# 3. Optional: build a wheel (dist/shared-0.3.0-py3-none-any.whl) to attach to a release or upload to an index.
uv build --package shared
```

Follow semver. While the version is 0.x, a breaking change bumps the minor version, as 0.2.0 did when the
modules moved into `auth` and `wp_migration`. That covers a breaking change to the Python API and dropping
support for a token version. This repository has no publishing pipeline yet, so the tag and the wheel are made
by hand.

## Use a tagged version from another project

Depend on a version range, and pin the exact tag in `[tool.uv.sources]` (replace the URL with wherever this
repository is hosted):

```toml
# pyproject.toml
dependencies = ["shared[drf,wp]>=0.2,<0.3"]

[tool.uv.sources]
shared = { git = "https://github.com/<org>/<repo>", subdirectory = "libs/shared", tag = "shared/v0.2.0" }
```

Then `uv lock` resolves the tag to a commit, and the lockfile keeps it. To take a new release, change the tag and
the range, and run `uv lock` again. Other ways to install the same tag:

```bash
pip install "shared[drf] @ git+https://github.com/<org>/<repo>@shared/v0.2.0#subdirectory=libs/shared"
uv add ./shared-0.2.0-py3-none-any.whl      # from a built wheel
```

Inside this repository the services use the workspace copy (`shared = { workspace = true }`), the main app with
`shared[drf,wp]>=0.2,<0.3` and the auth service with `shared[wp]>=0.2,<0.3`. So both always run the library's
current source; the range is checked when `uv lock` runs.
