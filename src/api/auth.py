"""Auth router — user registration and API-key generation.

Routes
------
* ``POST /auth/register``       — create a new user + FREE subscription.
* ``POST /auth/generate-key``   — issue a fresh API key for an existing user.

Future work
-----------
* ``POST /auth/login`` returning a short-lived JWT.
* A FastAPI ``Depends`` that resolves the *current* user from a
  ``Bearer`` token (JWT or an existing API key) — once that's in
  place, ``/auth/generate-key`` should stop accepting the email in
  the body and use the resolved user instead.
* A middleware that enforces ``Subscription.request_limit`` by
  counting ``ApiUsageLog`` rows per billing period.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.security import generate_api_key, hash_password
from src.database import ApiKey, Subscription, User, get_db
from src.schemas.user import (
    ApiKeyResponse,
    GenerateKeyRequest,
    UserCreate,
    UserResponse,
)


router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------- #
# POST /auth/register
# ---------------------------------------------------------------------- #
@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
def register(
    payload: UserCreate,
    db: Session = Depends(get_db),
) -> UserResponse:
    """Create a new user and a default FREE subscription (100 req / period).

    Returns ``201 Created`` with the public user shape on success.
    Returns ``409 Conflict`` if the email is already registered.
    """
    # Pre-check: a fast 409 before we hash the password, so the
    # typical "duplicate email" flow doesn't waste a bcrypt round.
    existing = db.execute(
        select(User).where(User.email == payload.email)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Email {payload.email!r} is already registered.",
        )

    # Build the user with the bcrypt-hashed password.
    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)

    try:
        db.flush()  # populates user.id without committing yet
    except IntegrityError:
        # Lost the race against another concurrent register; roll back
        # and surface the same 409 the pre-check would have.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Email {payload.email!r} is already registered.",
        ) from None

    # Default FREE tier. The 100 req/period is the same number the
    # marketing page quotes; tweak via Subscription on the admin side.
    subscription = Subscription(
        user_id=user.id,
        tier_name="FREE",
        request_limit=100,
    )
    db.add(subscription)

    db.commit()
    db.refresh(user)

    return UserResponse.model_validate(user)


# ---------------------------------------------------------------------- #
# POST /auth/generate-key
# ---------------------------------------------------------------------- #
@router.post(
    "/generate-key",
    response_model=ApiKeyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a new API key for an existing user",
)
def generate_key(
    payload: GenerateKeyRequest,
    db: Session = Depends(get_db),
) -> ApiKeyResponse:
    """Issue a fresh API key for the user identified by ``payload.email``.

    The response is the **only** place the raw key will ever appear.
    The server stores only the bcrypt hash; subsequent reads (e.g. a
    future ``GET /auth/keys`` listing) will return the prefix and
    metadata but never the raw key.

    Returns ``404 Not Found`` if the email is not registered.
    """
    user = db.execute(
        select(User).where(User.email == payload.email)
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No user with email {payload.email!r}.",
        )

    raw_key, hashed_key, key_prefix = generate_api_key()

    api_key = ApiKey(
        user_id=user.id,
        key_prefix=key_prefix,
        hashed_key=hashed_key,
        is_revoked=False,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    # The raw_key is included *only* here, at creation time.
    return ApiKeyResponse(
        id=api_key.id,
        key_prefix=api_key.key_prefix,
        raw_key=raw_key,
        created_at=api_key.created_at,
    )
