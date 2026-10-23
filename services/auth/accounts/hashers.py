"""Verifies passwords hashed by WordPress, so migrated users keep their old password.

The importer stores a WordPress hash as `wordpress$<hash as WordPress stored it>`. On a
successful login Django re-hashes the password with the preferred hasher (PBKDF2), because
this one is never first in PASSWORD_HASHERS, so each WordPress hash is used at most once.
This hasher only verifies: it never creates a hash.

Supported formats:
- `$wp$2y$...` (WordPress 6.8+): bcrypt over base64(HMAC-SHA384(password, key "wp-sha384")).
  The key is WordPress's fixed constant, not a secret.
- `$2y$...` / `$2b$...`: plain bcrypt, which WordPress stores when its algorithm is filtered.
Older phpass (`$P$...`) and MD5 hashes are not supported; the importer leaves those users
with an unusable password and reports them.
"""

import base64
import hashlib
import hmac

import bcrypt
from django.contrib.auth.hashers import BasePasswordHasher, mask_hash

ALGORITHM = "wordpress"
_PREFIXED_BCRYPT = "$wp$2"
_BCRYPT = ("$2y$", "$2b$", "$2a$")


def is_supported(wp_hash: str) -> bool:
    """Whether a WordPress `user_pass` value can be verified here."""
    return wp_hash.startswith(_PREFIXED_BCRYPT) or wp_hash.startswith(_BCRYPT)


def encode_wordpress_hash(wp_hash: str) -> str:
    """The value to store in User.password for a WordPress hash."""
    return f"{ALGORITHM}${wp_hash}"


class WordPressPasswordHasher(BasePasswordHasher):
    algorithm = ALGORITHM
    library = "bcrypt"

    def encode(self, password, salt):
        raise NotImplementedError("WordPress hashes are only verified, never created.")

    def decode(self, encoded):
        algorithm, wp_hash = encoded.split("$", 1)
        assert algorithm == self.algorithm  # noqa: S101 (Django's own hashers do the same)
        return {"algorithm": algorithm, "hash": wp_hash, "salt": ""}

    def verify(self, password, encoded):
        wp_hash = self.decode(encoded)["hash"]
        if wp_hash.startswith(_PREFIXED_BCRYPT):
            digest = hmac.new(b"wp-sha384", password.encode(), hashlib.sha384).digest()
            candidate, stored = base64.b64encode(digest), wp_hash[3:]
        elif wp_hash.startswith(_BCRYPT):
            # PHP's password_verify reads at most 72 bytes; newer bcrypt releases refuse more.
            candidate, stored = password.encode()[:72], wp_hash
        else:
            return False
        try:
            return bcrypt.checkpw(candidate, stored.encode())
        except ValueError:  # malformed hash
            return False

    def safe_summary(self, encoded):
        return {"algorithm": self.algorithm, "hash": mask_hash(self.decode(encoded)["hash"])}

    def must_update(self, encoded):
        return True

    def harden_runtime(self, password, encoded):
        pass
