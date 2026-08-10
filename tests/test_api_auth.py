"""Integration tests for API-key protection on ``POST /api/v1/price``.

Uses a **single shared** in-memory SQLite connection (``StaticPool``)
so that seed data written in a fixture is visible to the FastAPI
``get_db`` dependency override running in a different thread.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.security import generate_api_key, hash_password
from src.database.models import ApiKey, ApiUsageLog, Base, Subscription, User
from src.database.session import get_db

# ---------------------------------------------------------------------- #
# Shared in-memory database (StaticPool = single connection reused)
# ---------------------------------------------------------------------- #
_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = sessionmaker(
    bind=_engine, class_=Session, autoflush=False, autocommit=False,
)


def _override_get_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _setup_tables():
    """Create tables before each test; drop them afterward."""
    Base.metadata.create_all(bind=_engine)
    yield
    Base.metadata.drop_all(bind=_engine)


@pytest.fixture()
def client():
    from src.api import app

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _seed_user_with_key(
    limit: int = 100,
    revoked: bool = False,
) -> tuple[str, User]:
    """Insert a user + subscription + API key, return ``(raw_key, user)``."""
    db = _TestSession()
    user = User(email="test@example.com", hashed_password=hash_password("pw"))
    db.add(user)
    db.flush()

    sub = Subscription(user_id=user.id, tier_name="FREE", request_limit=limit)
    db.add(sub)
    db.flush()

    raw_key, hashed_key, key_prefix = generate_api_key()
    ak = ApiKey(
        user_id=user.id,
        key_prefix=key_prefix,
        hashed_key=hashed_key,
        is_revoked=revoked,
    )
    db.add(ak)
    db.commit()
    db.refresh(user)
    db.close()
    return raw_key, user


# Fake market data — avoid network.
_FAKE_MARKET = {"S": 150.0, "sigma": 0.25}


def _fake_market(_ticker: str):
    return _FAKE_MARKET


# ---------------------------------------------------------------------- #
# Tests
# ---------------------------------------------------------------------- #
class TestPricingAuth:
    PRICE_URL = "/api/v1/price"
    PAYLOAD = {
        "ticker": "AAPL",
        "strike_price": 155.0,
        "time_to_maturity": 0.25,
    }

    def test_missing_key_is_rejected(self, client: TestClient):
        """No X-API-Key header → 401 or 403."""
        resp = client.post(self.PRICE_URL, json=self.PAYLOAD)
        assert resp.status_code in (401, 403)

    def test_invalid_key_returns_401(self, client: TestClient):
        resp = client.post(
            self.PRICE_URL,
            json=self.PAYLOAD,
            headers={"X-API-Key": "bogus_key_1234567890"},
        )
        assert resp.status_code == 401

    def test_revoked_key_returns_401(self, client: TestClient):
        raw_key, _ = _seed_user_with_key(revoked=True)
        resp = client.post(
            self.PRICE_URL,
            json=self.PAYLOAD,
            headers={"X-API-Key": raw_key},
        )
        assert resp.status_code == 401

    @patch("src.api.get_market_inputs", side_effect=_fake_market)
    def test_valid_key_returns_200(self, _mock, client: TestClient):
        raw_key, _ = _seed_user_with_key(limit=10)
        resp = client.post(
            self.PRICE_URL,
            json=self.PAYLOAD,
            headers={"X-API-Key": raw_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "call_price" in data
        assert "put_price" in data

    @patch("src.api.get_market_inputs", side_effect=_fake_market)
    def test_rate_limit_exhaustion_returns_429(self, _mock, client: TestClient):
        raw_key, _ = _seed_user_with_key(limit=1)
        # First call succeeds (limit 1 → 0).
        resp1 = client.post(
            self.PRICE_URL, json=self.PAYLOAD, headers={"X-API-Key": raw_key},
        )
        assert resp1.status_code == 200

        # Second call is rate-limited.
        resp2 = client.post(
            self.PRICE_URL, json=self.PAYLOAD, headers={"X-API-Key": raw_key},
        )
        assert resp2.status_code == 429

    @patch("src.api.get_market_inputs", side_effect=_fake_market)
    def test_usage_log_created(self, _mock, client: TestClient):
        raw_key, _ = _seed_user_with_key(limit=10)
        client.post(
            self.PRICE_URL, json=self.PAYLOAD, headers={"X-API-Key": raw_key},
        )
        db = _TestSession()
        logs = db.query(ApiUsageLog).all()
        assert len(logs) == 1
        assert logs[0].endpoint == "/api/v1/price"
        assert logs[0].execution_time_ms > 0
        db.close()
