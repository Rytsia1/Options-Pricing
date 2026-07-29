"""Pydantic v2 schemas for the user / auth surface.

* :class:`UserCreate`      — request body for ``POST /auth/register``.
* :class:`UserResponse`    — response body for ``POST /auth/register``.
* :class:`GenerateKeyRequest` — request body for ``POST /auth/generate-key``.
* :class:`ApiKeyResponse`  — response body for ``POST /auth/generate-key``.

All response models set ``from_attributes=True`` so they can be built
directly from SQLAlchemy ORM instances via ``UserResponse.model_validate(user)``.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ---------------------------------------------------------------------- #
# User
# ---------------------------------------------------------------------- #
class UserCreate(BaseModel):
    """Request body for ``POST /auth/register``.

    Attributes
    ----------
    email : EmailStr
        A validated email address. We normalize it to lowercase and
        strip whitespace before persisting.
    password : str
        Plain-text password. Bcrypt-hashed server-side; never stored
        or logged. Enforced length bounds keep us safely inside
        bcrypt's 72-byte input window.
    """

    email: EmailStr
    password: str = Field(
        min_length=8,
        max_length=128,
        description="Plain-text password; bcrypt-hashed server-side.",
    )

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, v: object) -> object:
        """Trim whitespace and lowercase the email before validation."""
        if isinstance(v, str):
            return v.strip().lower()
        return v


class UserResponse(BaseModel):
    """Response body for ``POST /auth/register``.

    Attributes
    ----------
    id : int
        Server-assigned user id.
    email : str
        The normalized email (lowercased, trimmed).
    is_active : bool
        ``True`` for a healthy, non-suspended user. The underlying
        ``User`` table doesn't have an ``is_active`` column yet, so
        this field is always ``True`` for now; the field is included
        now so the API contract is forward-compatible when the column
        is added.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    is_active: bool = True


# ---------------------------------------------------------------------- #
# API key
# ---------------------------------------------------------------------- #
class GenerateKeyRequest(BaseModel):
    """Request body for ``POST /auth/generate-key``.

    The spec accepts a user's email directly here "for simplicity
    right now"; once a real auth middleware is in place (JWT or
    existing-API-key-based), this will become authenticated and the
    email field will be replaced by the resolved user.
    """

    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip().lower()
        return v


class ApiKeyResponse(BaseModel):
    """Response body for ``POST /auth/generate-key``.

    !!! danger "Raw key is shown ONCE"
        The ``raw_key`` field is **only** populated in the response to
        the initial ``POST /auth/generate-key`` call. The server stores
        only the bcrypt hash; subsequent reads of the key (via a
        future ``GET /auth/keys`` listing) will return the ``key_prefix``
        and metadata but never the raw key. Never log ``raw_key``,
        never store it client-side, never include it in any other
        response.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    key_prefix: str
    raw_key: str = Field(
        description=(
            "The full API key. **Only returned at creation time.** "
            "Store it now — the server cannot show it again."
        ),
    )
    created_at: datetime


__all__ = [
    "ApiKeyResponse",
    "GenerateKeyRequest",
    "UserCreate",
    "UserResponse",
]
