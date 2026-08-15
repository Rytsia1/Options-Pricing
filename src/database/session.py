"""SQLAlchemy 2.0 engine, session factory, and FastAPI dependency.

Local development
-----------------
The default ``DATABASE_URL`` is a local SQLite file
(``./options_pricing.db``). SQLite needs ``check_same_thread=False`` so
that the FastAPI worker thread pool can use connections created on
the main thread; we only apply that kwarg in the SQLite branch so the
PostgreSQL path uses psycopg2's default behavior.

Production
----------
Set the ``DATABASE_URL`` env var to a PostgreSQL DSN, e.g.::

    export DATABASE_URL="postgresql+psycopg2://user:pass@host:5432/options_pricing"

In production, schema management should be done via Alembic
(``alembic upgrade head``) — ``create_all()`` is a convenience for
local dev and the test suite, and is intentionally idempotent.

Public surface
--------------
* :data:`engine`       — the global :class:`sqlalchemy.Engine`.
* :data:`SessionLocal`  — the :class:`sessionmaker` factory.
* :func:`get_db`        — FastAPI ``Depends``-compatible generator that
                          yields a session and always closes it.
* :func:`init_db`       — explicit ``create_all()`` (called on import
                          for dev convenience; safe to call again).

CLI smoke test::

    python -m src.database.session

This creates the SQLite file (if missing) and prints the table list,
which is a quick way to verify that imports resolve and ``Base.metadata``
sees all four models.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import settings
from src.database.models import Base


# ---------------------------------------------------------------------- #
# Engine & session factory
# ---------------------------------------------------------------------- #
DATABASE_URL: str = settings.DATABASE_URL


def _engine_kwargs(url: str) -> dict[str, object]:
    """Per-Driver-engine keyword arguments.

    SQLite requires ``check_same_thread=False`` when the same engine
    is shared across threads (which is exactly what FastAPI does).
    PostgreSQL via psycopg2 uses the driver defaults; passing
    ``check_same_thread`` to a non-sqlite DSN would actually raise.
    """
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {}


engine: Engine = create_engine(
    DATABASE_URL,
    future=True,           # 2.0-style result objects
    pool_pre_ping=True,    # transparently reconnect on dropped connections
    **_engine_kwargs(DATABASE_URL),
)

# Explicit `class_=Session` is the SQLAlchemy 2.0 idiom — it makes
# mypy/pyright happy and the `Session` type visible to IDE tooling.
SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


# ---------------------------------------------------------------------- #
# Schema bootstrap (dev convenience)
# ---------------------------------------------------------------------- #
def init_db() -> None:
    """Create all tables that don't yet exist. Idempotent."""
    # `checkfirst=True` is the default; calling create_all repeatedly
    # is safe and only emits the missing DDL.
    Base.metadata.create_all(bind=engine)


# Run on import so a fresh checkout "just works" locally. In production
# this line is a no-op because Alembic manages the schema, and any
# conflicting migration would have been caught long before this import.
init_db()


# ---------------------------------------------------------------------- #
# FastAPI dependency
# ---------------------------------------------------------------------- #
def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session, closing it on exit.

    Use as a FastAPI dependency::

        @app.get("/me")
        def me(db: Session = Depends(get_db)):
            return db.execute(...).scalar()

    The ``try / finally`` guarantees the session is closed even if the
    route raises. ``expire_on_commit=False`` on the factory means
    detached instances remain usable after the session is closed.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------- #
# CLI smoke test
# ---------------------------------------------------------------------- #
if __name__ == "__main__":  # pragma: no cover
    # Re-run init_db explicitly so the printed tables reflect what's
    # actually in the DB even if import-time init was skipped.
    init_db()

    inspector = inspect(engine)
    tables = sorted(inspector.get_table_names())
    print(f"Database: {DATABASE_URL}")
    print(f"Tables  : {', '.join(tables) if tables else '(none)'}")
    for t in tables:
        cols = ", ".join(c["name"] for c in inspector.get_columns(t))
        print(f"  - {t}({cols})")
