"""Password hashing and API-key generation utilities.

Two responsibilities, both intentionally tiny:

1. **User passwords** are hashed and verified with bcrypt via ``passlib``.
   ``CryptContext(schemes=["bcrypt"], deprecated="auto")`` means that
   the first scheme is used for new hashes, and any older schemes
   (none yet) are auto-upgraded on the next successful verify.

2. **API keys** are generated with :func:`secrets.token_urlsafe` (32
   random bytes → ~43 chars of URL-safe base64), prefixed with a short,
   human-readable namespace (``"opk_"``) so the key is identifiable
   in logs and dashboards, and then bcrypt-hashed exactly the same
   way user passwords are. The first ``API_KEY_PREFIX_LENGTH`` chars
   of the raw key are stored alongside the hash for fast lookups
   and so the UI can show "key ``opk_…`` was used" without ever
   revealing the secret.

Why bcrypt for API keys too? Bcrypt is intentionally slow (~100ms
per hash at the default cost), which is fine for our throughput and
keeps the codebase consistent with one canonical hashing path. If
we ever need to validate millions of keys per second (we don't), the
canonical SHA-256-with-a-server-secret trade-off is one function
swap away.
"""

from __future__ import annotations

import secrets

from passlib.context import CryptContext


# ---------------------------------------------------------------------- #
# Module-level constants
# ---------------------------------------------------------------------- #
# Visible namespace at the start of every API key. Short, unambiguous,
# and easy to grep for in logs. Adjust here, not in callers.
API_KEY_NAMESPACE: str = "opk_"

# Number of leading characters of the raw key we store in
# ``ApiKey.key_prefix``. Per spec: 4. The prefix is what gets indexed
# for "find candidate key by prefix, then bcrypt-verify".
API_KEY_PREFIX_LENGTH: int = 4

# Raw-key size in *bytes*. 32 bytes = 256 bits of entropy, which is
# well above the OWASP recommendation for API tokens.
API_KEY_TOKEN_BYTES: int = 32


# ---------------------------------------------------------------------- #
# Password hashing
# ---------------------------------------------------------------------- #
# `deprecated="auto"` means new hashes use the first scheme, and any
# older hashes (if/when we add more schemes) are silently re-hashed
# to the current scheme on the next successful verify.
pwd_context: CryptContext = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain*.

    Bcrypt silently truncates inputs longer than 72 bytes; the
    ``UserCreate`` Pydantic schema enforces ``max_length=128`` which
    keeps us in the safe zone for essentially all real passwords.
    """
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return ``True`` iff *plain* matches the bcrypt-hashed *hashed*."""
    return pwd_context.verify(plain, hashed)


# ---------------------------------------------------------------------- #
# API-key generation
# ---------------------------------------------------------------------- #
def generate_api_key() -> tuple[str, str, str]:
    """Generate a fresh API key.

    Returns
    -------
    tuple[str, str, str]
        ``(raw_key, hashed_key, key_prefix)`` where:

        * ``raw_key`` is what we hand back to the user **once** at
          creation time. They store it; we never see it again.
        * ``hashed_key`` is the bcrypt hash of ``raw_key`` and what
          we persist in the database.
        * ``key_prefix`` is the first ``API_KEY_PREFIX_LENGTH`` chars
          of ``raw_key`` (e.g. ``"opk_"`` plus one more char). We
          use it for the indexed lookup and the dashboard display.

    The raw key looks like ``opk_<43 url-safe chars>`` (~47 chars
    total, ~256 bits of entropy from the underlying random bytes).
    """
    token: str = secrets.token_urlsafe(API_KEY_TOKEN_BYTES)
    raw_key: str = f"{API_KEY_NAMESPACE}{token}"
    key_prefix: str = raw_key[:API_KEY_PREFIX_LENGTH]
    hashed_key: str = hash_password(raw_key)
    return raw_key, hashed_key, key_prefix


__all__ = [
    "API_KEY_NAMESPACE",
    "API_KEY_PREFIX_LENGTH",
    "API_KEY_TOKEN_BYTES",
    "generate_api_key",
    "hash_password",
    "pwd_context",
    "verify_password",
]
