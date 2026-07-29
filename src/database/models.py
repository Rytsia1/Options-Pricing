"""SQLAlchemy 2.0 ORM models for the Options Pricing Engine SaaS layer.

Schema overview
---------------
::

    User ──── 1:1 ───── Subscription
      │
      └───── 1:N ────── ApiKey ──── 1:N ────── ApiUsageLog

All tables use the modern SQLAlchemy 2.0 declarative style:
``DeclarativeBase`` + ``Mapped[...]`` annotations + ``mapped_column(...)``.
No legacy ``Column = Column(...)`` patterns.

Conventions
-----------
* Primary keys are auto-incrementing 64-bit integers.
* All FKs use ``ondelete="CASCADE"`` so deleting a user cleans up
  subscriptions, API keys, and usage logs in a single statement.
* The ``Subscription`` table has a ``UniqueConstraint("user_id")`` to
  enforce the 1:1 relationship at the DB level (defense in depth on top
  of the ORM's ``uselist=False``).
* Timestamps use ``server_default=func.now()`` so they're stamped by
  the database, not by the application clock (avoids clock-skew bugs
  in multi-instance deployments).

Future work
-----------
* Wire these models into Alembic::

      alembic init alembic
      # ...edit alembic/env.py to point at Base.metadata...
      alembic revision --autogenerate -m "initial schema"
      alembic upgrade head

* Add a small ``auth.py`` with ``hash_password`` / ``verify_password``
  helpers built on top of ``passlib.context.CryptContext(schemes=["bcrypt"])``.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------- #
# Declarative base
# ---------------------------------------------------------------------- #
class Base(DeclarativeBase):
    """Project-wide SQLAlchemy 2.0 declarative base.

    Using ``DeclarativeBase`` (instead of the legacy ``declarative_base()``
    factory) is the documented 2.0 idiom and plays well with Alembic's
    autogenerate.
    """


# ---------------------------------------------------------------------- #
# User
# ---------------------------------------------------------------------- #
class User(Base):
    """A registered user of the Options Pricing Engine."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # --- relationships ------------------------------------------------- #
    # One-to-one: a user has at most one subscription. `uselist=False`
    # makes the relationship return a single `Subscription` instead of
    # a list. `cascade="all, delete-orphan"` means deleting the user
    # deletes their subscription automatically.
    subscription: Mapped["Subscription | None"] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

    # One-to-many: a user can have many API keys (e.g. one per device
    # or per integration). `cascade` keeps the keys in sync with the
    # user lifecycle.
    api_keys: Mapped[list["ApiKey"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"


# ---------------------------------------------------------------------- #
# Subscription
# ---------------------------------------------------------------------- #
class Subscription(Base):
    """A user's billing plan (one-to-one with :class:`User`)."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        # Enforce the 1:1 at the DB level: a user_id can only appear once.
        UniqueConstraint("user_id", name="uq_subscriptions_user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tier_name: Mapped[str] = mapped_column(String(50), nullable=False)
    # `request_limit` is the number of API calls per billing period.
    # Use -1 (or a sentinel constant) to mean "unlimited".
    request_limit: Mapped[int] = mapped_column(Integer, nullable=False)

    # Back-reference to the owning user.
    user: Mapped["User"] = relationship(back_populates="subscription")

    def __repr__(self) -> str:
        return (
            f"<Subscription id={self.id} user_id={self.user_id} "
            f"tier={self.tier_name!r} limit={self.request_limit}>"
        )


# ---------------------------------------------------------------------- #
# ApiKey
# ---------------------------------------------------------------------- #
class ApiKey(Base):
    """An API key issued to a user.

    The raw key is **only** ever shown to the user once (at creation
    time). What we store is:

    * ``key_prefix``  — the first ~8 characters of the raw key, used
      for fast lookup and shown in dashboards.
    * ``hashed_key``  — a bcrypt hash of the full raw key. Verification
      on each request hashes the supplied key and compares.
    """

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Short, non-secret prefix shown in the UI; also the lookup key
    # for "find candidate key by prefix, then bcrypt-verify".
    key_prefix: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        index=True,
    )
    # Bcrypt hash of the full key. ~60 chars; never log this.
    hashed_key: Mapped[str] = mapped_column(String(255), nullable=False)
    is_revoked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
        index=True,  # fast "give me all active keys" filters
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # --- relationships ------------------------------------------------- #
    user: Mapped["User"] = relationship(back_populates="api_keys")

    # One-to-many: every request that uses this key appends a usage
    # log row for billing / analytics.
    usage_logs: Mapped[list["ApiUsageLog"]] = relationship(
        back_populates="api_key",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<ApiKey id={self.id} user_id={self.user_id} "
            f"prefix={self.key_prefix!r} revoked={self.is_revoked}>"
        )


# ---------------------------------------------------------------------- #
# ApiUsageLog
# ---------------------------------------------------------------------- #
class ApiUsageLog(Base):
    """A single API call's record. Append-only in production."""

    __tablename__ = "api_usage_logs"
    __table_args__ = (
        # Composite index for the most common query: "give me this key's
        # usage between time T1 and T2". Indexes are listed in column
        # order to make range scans efficient.
        Index("ix_api_usage_logs_key_ts", "api_key_id", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_key_id: Mapped[int] = mapped_column(
        ForeignKey("api_keys.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The endpoint called, e.g. "/api/v1/price".
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    # Wall-clock execution time on the server, in milliseconds.
    execution_time_ms: Mapped[float] = mapped_column(Float, nullable=False)
    # When the request landed. Defaulted by the DB so it's consistent
    # across all app instances.
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Back-reference to the API key.
    api_key: Mapped["ApiKey"] = relationship(back_populates="usage_logs")

    def __repr__(self) -> str:
        return (
            f"<ApiUsageLog id={self.id} api_key_id={self.api_key_id} "
            f"endpoint={self.endpoint!r} t={self.execution_time_ms:.2f}ms>"
        )
