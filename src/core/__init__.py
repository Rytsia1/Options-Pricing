"""Core utilities: security, hashing, API-key generation, etc.

Keep this package dependency-light: no FastAPI, no SQLAlchemy, no
pydantic. Anything in here should be importable from anywhere in the
codebase (including Alembic ``env.py``, CLI scripts, and tests) without
triggering a heavy import graph.
"""
