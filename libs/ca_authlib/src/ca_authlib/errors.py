class TokenError(Exception):
    """The token is malformed, expired, forged, or not meant for this service."""


class InvalidClaims(TokenError):
    """The token verified, but its claims are not something we accept."""


class KeysUnavailable(Exception):
    """The signing keys cannot be obtained, so a token can be neither accepted nor
    rejected. Distinct from TokenError so callers can answer 503, not 401."""


class IntrospectionUnavailable(Exception):
    """The auth service could not be asked whether a token is still good."""


class InvalidIntrospection(ValueError):
    """The auth service's introspection response was not in the agreed shape."""
