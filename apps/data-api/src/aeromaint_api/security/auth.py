import base64
import hashlib
import hmac
import json
import time
from collections.abc import Mapping
from typing import Any, Protocol, cast

from aeromaint_api.security.errors import SecurityError
from aeromaint_api.security.models import Principal, Role


class Authenticator(Protocol):
    def authenticate(self, authorization: str | None) -> Principal: ...


def _decode_segment(segment: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
    except (ValueError, TypeError) as exc:
        raise _invalid_token() from exc


def _invalid_token(detail: str = "The bearer token is invalid.") -> SecurityError:
    return SecurityError(
        401,
        "invalid_token",
        "Authentication failed",
        detail,
        {"WWW-Authenticate": 'Bearer error="invalid_token"'},
    )


class DevelopmentJwtAuthenticator:
    """Minimal HS256 JWT verifier for local development; no unverified claims are trusted."""

    def __init__(self, secret: str, issuer: str, audience: str) -> None:
        self._secret = secret.encode()
        self._issuer = issuer
        self._audience = audience

    def authenticate(self, authorization: str | None) -> Principal:
        if authorization is None or not authorization.startswith("Bearer "):
            raise SecurityError(
                401,
                "authentication_required",
                "Authentication required",
                "A bearer token is required.",
                {"WWW-Authenticate": "Bearer"},
            )
        token = authorization.removeprefix("Bearer ")
        parts = token.split(".")
        if len(parts) != 3 or not all(parts):
            raise _invalid_token()
        encoded_header, encoded_payload, encoded_signature = parts
        try:
            header = cast(dict[str, Any], json.loads(_decode_segment(encoded_header)))
            payload = cast(dict[str, Any], json.loads(_decode_segment(encoded_payload)))
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
            raise _invalid_token() from exc
        if header.get("alg") != "HS256" or header.get("typ") not in (None, "JWT"):
            raise _invalid_token("The bearer token algorithm is not accepted.")
        signing_input = f"{encoded_header}.{encoded_payload}".encode()
        expected = hmac.new(self._secret, signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _decode_segment(encoded_signature)):
            raise _invalid_token()
        self._validate_claims(payload)
        try:
            roles = frozenset(Role(role) for role in payload["roles"])
        except (KeyError, TypeError, ValueError) as exc:
            raise _invalid_token("The bearer token contains invalid roles.") from exc
        if not roles:
            raise _invalid_token("The bearer token must contain at least one role.")
        return Principal(subject=cast(str, payload["sub"]), roles=roles)

    def _validate_claims(self, claims: Mapping[str, Any]) -> None:
        now = int(time.time())
        if not isinstance(claims.get("sub"), str) or not claims["sub"]:
            raise _invalid_token("The bearer token subject is missing.")
        if claims.get("iss") != self._issuer or claims.get("aud") != self._audience:
            raise _invalid_token("The bearer token issuer or audience is invalid.")
        exp = claims.get("exp")
        if not isinstance(exp, int) or isinstance(exp, bool) or exp <= now:
            raise _invalid_token("The bearer token is expired or has no valid expiry.")
        nbf = claims.get("nbf")
        if nbf is not None and (not isinstance(nbf, int) or isinstance(nbf, bool) or nbf > now):
            raise _invalid_token("The bearer token is not yet valid.")
