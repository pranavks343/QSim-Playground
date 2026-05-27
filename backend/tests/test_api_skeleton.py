from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from api.main import create_app
from infra.settings import get_settings


def test_health_returns_expected_shape() -> None:
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert isinstance(data["db_reachable"], bool)
    assert isinstance(data["gemini_reachable"], bool)
    assert isinstance(data["version"], str)


def test_protected_route_without_authorization_returns_401() -> None:
    client = TestClient(create_app())

    response = client.get("/api/profile/me")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["detail"] == "Invalid or expired token"


def test_protected_route_with_malformed_token_returns_401() -> None:
    client = TestClient(create_app())

    response = client.get("/api/profile/me", headers={"Authorization": "Bearer not-a-jwt"})

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_protected_route_with_expired_token_returns_401(monkeypatch: MonkeyPatch) -> None:
    _configure_settings_env(monkeypatch)
    get_settings.cache_clear()
    client = TestClient(create_app())
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "email": "expired@example.com",
            "aud": "authenticated",
            "exp": datetime.now(tz=UTC) - timedelta(minutes=1),
        },
        "jwt-secret-for-tests-with-enough-entropy",
        algorithm="HS256",
    )

    response = client.get("/api/profile/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_request_id_header_added_on_every_response() -> None:
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"]


def test_cors_headers_present_for_whitelisted_origin() -> None:
    client = TestClient(create_app())

    response = client.get("/api/health", headers={"Origin": "http://localhost:3000"})

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"


def _configure_settings_env(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEYS", "gemini-key-for-tests")
    monkeypatch.setenv("SUPABASE_URL", "https://qsim-test.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", _jwt_like_value("anon"))
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", _jwt_like_value("service"))
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "jwt-secret-for-tests-with-enough-entropy")
    monkeypatch.setenv("SENTRY_DSN", "")
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:3000")


def _jwt_like_value(prefix: str) -> str:
    return jwt.encode(
        {"sub": prefix, "aud": "authenticated", "exp": datetime.now(tz=UTC) + timedelta(days=1)},
        "fixture-signing-key-with-enough-entropy",
        algorithm="HS256",
    )
