# ca-authlib

The code the main app and the auth service share, so the two sides of a token cannot drift apart. Keep it small:
a module belongs here only if more than one service imports it.

## What is in it

| Module | What it does |
|---|---|
| `claims` | The token contract: `Claims`, `Role`, `issue_claims`, `encode_claims` / `decode_claims`. Tokens carry a version (`v`), so a new format can roll out without a simultaneous deploy |
| `verify` | `TokenVerifier` and `JWKSClient`: check a token's signature, issuer, audience, expiry and version against the auth service's public keys (cached; no network call per request) |
| `drf` | Django REST framework adapter (needs the `drf` extra): `JWTAuthentication` and `require_role(...)` |
| `ids` | `user_id_from_wp_id()`: the deterministic user id both migrations derive from a WordPress id |
| `errors` | The exceptions the other modules raise |
| `testing` | `TestKey`, for signing tokens in tests (not for production use) |

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
from ca_authlib.claims import Role
from ca_authlib.drf import JWTAuthentication, require_role


class EditBrand(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [require_role(Role.EDITOR)]  # fresh=True also asks auth for current roles
```

**Anywhere else:** verify a token by hand.

```python
from ca_authlib.verify import JWKSClient, TokenVerifier, http_fetch

verifier = TokenVerifier(
    JWKSClient(http_fetch("http://auth:8001/.well-known/jwks.json")),
    issuer="brand-reviews-auth",
    audience="brand-reviews-app",
    accepted_versions=[1],
)
claims = verifier.verify(token)  # raises TokenError if it is not valid
claims.sub, claims.has_role("editor")
```

## Test it

No service is needed:

```bash
uv run --package ca-authlib --group test pytest libs/ca_authlib
```

## Publish a tagged version

The version is in two places: `version` in `pyproject.toml` and `__version__` in `src/ca_authlib/__init__.py`.

```bash
# 1. Bump both, then run the tests (above).
# 2. Commit and tag. The tag is ca-authlib/vX.Y.Z, so the library can be released on its own.
git commit -am "ca-authlib 0.2.0"
git tag ca-authlib/v0.2.0
git push origin main ca-authlib/v0.2.0

# 3. Optional: build a wheel (dist/ca_authlib-0.2.0-py3-none-any.whl) to attach to a release or upload to an index.
uv build --package ca-authlib
```

Follow semver: a breaking change to the Python API, or dropping support for a token version, is a major bump.
This repository has no publishing pipeline yet, so the tag and the wheel are made by hand.

## Use a tagged version from another project

Depend on a version range, and pin the exact tag in `[tool.uv.sources]` (replace the URL with wherever this
repository is hosted):

```toml
# pyproject.toml
dependencies = ["ca-authlib[drf]>=0.2,<0.3"]

[tool.uv.sources]
ca-authlib = { git = "https://github.com/<org>/brand-reviews", subdirectory = "libs/ca_authlib", tag = "ca-authlib/v0.2.0" }
```

Then `uv lock` resolves the tag to a commit, and the lockfile keeps it. To take a new release, change the tag and
the range, and run `uv lock` again. Other ways to install the same tag:

```bash
pip install "ca-authlib[drf] @ git+https://github.com/<org>/brand-reviews@ca-authlib/v0.2.0#subdirectory=libs/ca_authlib"
uv add ./ca_authlib-0.2.0-py3-none-any.whl      # from a built wheel
```

Inside this repository the two services use the workspace copy (`ca-authlib = { workspace = true }`) with the
range `>=0.1,<0.2`, so they always run the library's current source; the range is checked when `uv lock` runs.
