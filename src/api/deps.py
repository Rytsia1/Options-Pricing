"""FastAPI dependencies for API-key authentication.

Two dependencies form a chain:

1. :func:`get_api_key` — extracts the raw key from the ``X-API-Key``
   request header.  FastAPI auto-returns 403 if the header is missing.
2. :func:`verify_api_key` — looks up the key by its 4-char prefix,
   bcrypt-verifies the full key, and returns the owning
   :class:`~src.database.models.User` together with their
   :class:`~src.database.models.Subscription` and the matched
   :class:`~src.database.models.ApiKey`.

Usage in a route::

    from src.api.deps import verify_api_key

    @app.post("/api/v1/price")
    def price_option(
        ...,
        auth: dict = Depends(verify_api_key),
    ):
        user = auth["user"]
        subscription = auth["subscription"]
        api_key = auth["api_key"]
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from src.core.security import pwd_context
from src.database import ApiKey, User, get_db

# ---------------------------------------------------------------------- #
# Header extractor
# ---------------------------------------------------------------------- #
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)


def get_api_key(api_key: str = Depends(_api_key_header)) -> str:
    """Return the raw API key string from the ``X-API-Key`` header.

    If the header is missing, FastAPI's ``APIKeyHeader(auto_error=True)``
    raises 403 automatically — this function never sees the call.
    """
    return api_key


# ---------------------------------------------------------------------- #
# Full verification
# ---------------------------------------------------------------------- #
def verify_api_key(
    api_key: str = Depends(get_api_key),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Authenticate an incoming request by its API key.

    Steps
    -----
    1. Extract the first 4 characters of the supplied key as the
       ``key_prefix``.
    2. Query all non-revoked ``ApiKey`` rows whose ``key_prefix``
       matches (there may be more than one — collisions are possible
       but rare with 4 chars of a URL-safe-base64 key).
    3. For each candidate, verify the raw key against the stored
       bcrypt hash using ``passlib``.
    4. On the first match, eagerly load the owning ``User`` and their
       ``Subscription``, then return them as a dict.

    Raises
    ------
    HTTPException 401
        If no matching key is found, the key is revoked, or the
        bcrypt verification fails for all candidates.

    Returns
    -------
    dict
        ``{"user": User, "subscription": Subscription, "api_key": ApiKey}``
    """
    prefix = api_key[:4]

    # Fetch candidate keys by prefix, joining in the user and their
    # subscription so we don't need a second round-trip.
    stmt = (
        select(ApiKey)
        .where(ApiKey.key_prefix == prefix, ApiKey.is_revoked.is_(False))
        .options(
            joinedload(ApiKey.user).joinedload(User.subscription),
        )
    )
    candidates = db.execute(stmt).scalars().unique().all()

    for candidate in candidates:
        if pwd_context.verify(api_key, candidate.hashed_key):
            user = candidate.user
            subscription = user.subscription
            if subscription is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User has no active subscription.",
                )
            return {
                "user": user,
                "subscription": subscription,
                "api_key": candidate,
            }

    # No candidate matched — invalid or revoked key.
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or revoked API key.",
    )
