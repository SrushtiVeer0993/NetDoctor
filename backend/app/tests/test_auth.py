"""
Auth flow test. Requires DATABASE_URL to point at a reachable Postgres
instance (see docker-compose.yml) — this is an integration test, not a
pure unit test, since Phase 1 has no repository abstraction yet.
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_register_and_login():
    email = "pytest-user@example.com"
    password = "TestPassword123!"

    # TestClient must be used as a context manager so the lifespan startup
    # handler (table creation) actually runs before requests are sent.
    with TestClient(app) as ctx_client:
        reg = ctx_client.post("/api/auth/register", json={"email": email, "password": password})
        assert reg.status_code in (201, 400)  # 400 if already registered from a previous run

        login = ctx_client.post("/api/auth/login", json={"email": email, "password": password})
        assert login.status_code == 200
        assert "access_token" in login.json()
