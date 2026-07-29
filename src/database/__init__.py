"""Database package for the Options Pricing Engine SaaS layer.

This package bundles the SQLAlchemy 2.0 ORM models, the engine / session
factory, and the FastAPI ``get_db`` dependency. Importing from
``src.database`` instead of the individual sub-modules keeps the public
surface tiny and lets downstream code (the API routers, the future
Alembic ``env.py``, the auth layer) read like a single import line.

Typical usage
-------------
::

    from src.database import User, Subscription, ApiKey, ApiUsageLog, get_db

    @app.post("/auth/register")
    def register(payload: RegisterIn, db: Session = Depends(get_db)):
        user = User(email=payload.email, hashed_password=hash(payload.password))
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

The actual ORM classes and the engine live in the sibling modules:

* :mod:`src.database.models`  — ``Base`` + ``User`` / ``Subscription`` /
  ``ApiKey`` / ``ApiUsageLog``.
* :mod:`src.database.session` — ``engine``, ``SessionLocal``,
  ``get_db``.
"""

from src.database.models import (
    ApiKey,
    ApiUsageLog,
    Base,
    Subscription,
    User,
)
from src.database.session import SessionLocal, engine, get_db

__all__ = [
    "ApiKey",
    "ApiUsageLog",
    "Base",
    "SessionLocal",
    "Subscription",
    "User",
    "engine",
    "get_db",
]
