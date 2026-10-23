"""What can go wrong when checking a token. The split matters for the HTTP answer:
a TokenError means "this token is no good" (401); the *Unavailable errors mean "we
couldn't find out" (503), and must never be treated as either a yes or a no."""


class TokenError(Exception):
    """The token is malformed, expired, forged, or not meant for this service."""


class InvalidClaims(TokenError):
    """The signature is fine, but the claims are missing or the wrong type."""


class KeysUnavailable(Exception):
    """The auth service's public keys can't be fetched, so the token can't be checked."""


class IntrospectionUnavailable(Exception):
    """The auth service couldn't be asked whether a token is still good."""


class InvalidIntrospection(ValueError):
    """The auth service's introspection answer wasn't in the agreed shape."""
