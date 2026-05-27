from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

import api.routes.profile as profile_routes
import api.routes.runs as run_routes
from api.deps import AuthenticatedUser, get_current_user
from api.main import create_app
from core.templates import get_template


class FakeResult:
    def __init__(self, data: list[dict[str, Any]] | dict[str, Any]) -> None:
        self.data = data


class FakeQuery:
    def __init__(self, db: FakeSupabaseClient, table_name: str) -> None:
        self._db = db
        self._table_name = table_name
        self._operation = "select"
        self._payload: dict[str, Any] = {}
        self._filters: list[tuple[str, str, Any]] = []
        self._limit: int | None = None
        self._single = False

    def select(self, _columns: str) -> FakeQuery:
        self._operation = "select"
        return self

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self._operation = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._operation = "update"
        self._payload = payload
        return self

    def delete(self) -> FakeQuery:
        self._operation = "delete"
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def gt(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("gt", column, value))
        return self

    def lt(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("lt", column, value))
        return self

    def is_(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("is", column, value))
        return self

    def order(self, _column: str, desc: bool = False) -> FakeQuery:
        del desc
        return self

    def limit(self, value: int) -> FakeQuery:
        self._limit = value
        return self

    def single(self) -> FakeQuery:
        self._single = True
        return self

    def execute(self) -> FakeResult:
        if self._operation == "insert":
            return FakeResult([self._db.insert(self._table_name, self._payload)])
        if self._operation == "update":
            return FakeResult(self._db.update(self._table_name, self._payload, self._filters))
        if self._operation == "delete":
            return FakeResult(self._db.delete(self._table_name, self._filters))
        rows = self._db.select(self._table_name, self._filters)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._single:
            return FakeResult(rows[0] if rows else {})
        return FakeResult(rows)


class FakeSupabaseClient:
    def __init__(self, user_id: UUID, forbidden_ids: set[str] | None = None) -> None:
        self.user_id = str(user_id)
        self.forbidden_ids = forbidden_ids or set()
        now = datetime.now(tz=UTC).isoformat()
        self.tables: dict[str, list[dict[str, Any]]] = {
            "runs": [],
            "run_events": [],
            "users_profile": [
                {
                    "id": self.user_id,
                    "tier": "free",
                    "monthly_runs_used": 3,
                    "quota_reset_at": now,
                }
            ],
        }
        self._event_id = 1

    def table(self, table_name: str) -> FakeQuery:
        return FakeQuery(self, table_name)

    def insert(self, table_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        row = payload.copy()
        if table_name == "runs":
            row.setdefault("id", str(uuid4()))
            row.setdefault("created_at", datetime.now(tz=UTC).isoformat())
            row.setdefault("completed_at", None)
            row.setdefault("deleted_at", None)
        if table_name == "run_events":
            row.setdefault("id", self._event_id)
            self._event_id += 1
            row.setdefault("created_at", datetime.now(tz=UTC).isoformat())
        self.tables.setdefault(table_name, []).append(row)
        return row

    def select(self, table_name: str, filters: list[tuple[str, str, Any]]) -> list[dict[str, Any]]:
        rows = [row.copy() for row in self.tables.get(table_name, [])]
        for operator, column, value in filters:
            if column == "id" and str(value) in self.forbidden_ids:
                raise PermissionError("forbidden")
            if operator == "eq":
                rows = [row for row in rows if str(row.get(column)) == str(value)]
            elif operator == "gt":
                rows = [row for row in rows if row.get(column, 0) > value]
            elif operator == "lt":
                rows = [row for row in rows if str(row.get(column, "")) < str(value)]
            elif operator == "is" and value == "null":
                rows = [row for row in rows if row.get(column) is None]
        if table_name == "runs":
            rows = [row for row in rows if str(row.get("user_id")) == self.user_id]
        if table_name == "run_events":
            owned_run_ids = {
                row["id"] for row in self.tables["runs"] if row["user_id"] == self.user_id
            }
            rows = [row for row in rows if row.get("run_id") in owned_run_ids]
        return rows

    def update(
        self,
        table_name: str,
        payload: dict[str, Any],
        filters: list[tuple[str, str, Any]],
    ) -> list[dict[str, Any]]:
        rows = self.select(table_name, filters)
        for row in self.tables.get(table_name, []):
            if any(row.get("id") == selected.get("id") for selected in rows):
                row.update(payload)
        return [row | payload for row in rows]

    def delete(self, table_name: str, filters: list[tuple[str, str, Any]]) -> list[dict[str, Any]]:
        rows = self.select(table_name, filters)
        ids = {row.get("id") for row in rows}
        self.tables[table_name] = [
            row for row in self.tables.get(table_name, []) if row.get("id") not in ids
        ]
        return rows


@pytest.fixture()
def user_id() -> UUID:
    return uuid4()


@pytest.fixture()
def fake_db(user_id: UUID) -> FakeSupabaseClient:
    return FakeSupabaseClient(user_id)


@pytest.fixture()
def client(
    monkeypatch: MonkeyPatch,
    fake_db: FakeSupabaseClient,
    user_id: UUID,
) -> Iterator[TestClient]:
    app = create_app()

    def fake_current_user(request: Request) -> AuthenticatedUser:
        request.state.bearer_jwt = "test-jwt"
        request.state.user_id = str(user_id)
        return AuthenticatedUser(
            id=user_id,
            email="user@example.com",
            tier="free",
            monthly_runs_used=3,
            quota_remaining=47,
        )

    async def noop_execute_pipeline_background(*args: Any, **kwargs: Any) -> None:
        del args, kwargs

    async def noop_check_quota(*args: Any, **kwargs: Any) -> None:
        del args, kwargs

    async def noop_check_rate_limit(*args: Any, **kwargs: Any) -> None:
        del args, kwargs

    app.dependency_overrides[get_current_user] = fake_current_user
    monkeypatch.setattr(run_routes, "_client_for_request", lambda _request: fake_db)
    monkeypatch.setattr(run_routes, "execute_pipeline_background", noop_execute_pipeline_background)
    monkeypatch.setattr(run_routes, "check_quota", noop_check_quota)
    monkeypatch.setattr(run_routes, "check_rate_limit", noop_check_rate_limit)
    monkeypatch.setattr(profile_routes, "get_user_client", lambda _bearer_jwt: fake_db)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_create_run_from_template_success(client: TestClient) -> None:
    response = client.post(
        "/api/runs",
        json={"input_source": "template", "template_name": "portfolio"},
    )

    assert response.status_code == 201
    assert UUID(response.json()["run_id"])
    assert response.json()["status"] == "queued"


def test_create_run_without_auth_returns_401() -> None:
    response = TestClient(create_app()).post(
        "/api/runs",
        json={"input_source": "template", "template_name": "portfolio"},
    )

    assert response.status_code == 401


def test_create_run_invalid_body_returns_422(client: TestClient) -> None:
    response = client.post("/api/runs", json={"input_source": "template"})

    assert response.status_code == 422


def test_create_run_from_ir_success(client: TestClient) -> None:
    response = client.post(
        "/api/runs",
        json={"input_source": "ir", "problem_ir": get_template("knapsack").to_dict()},
    )

    assert response.status_code == 201


def test_list_runs_success(client: TestClient) -> None:
    client.post("/api/runs", json={"input_source": "template", "template_name": "portfolio"})

    response = client.get("/api/runs")

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1


def test_list_runs_validation_failure(client: TestClient) -> None:
    response = client.get("/api/runs?limit=101")

    assert response.status_code == 422


def test_get_run_success(client: TestClient) -> None:
    created = client.post(
        "/api/runs",
        json={"input_source": "template", "template_name": "portfolio"},
    ).json()

    response = client.get(f"/api/runs/{created['run_id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["run_id"]


def test_get_run_not_found_returns_404(client: TestClient) -> None:
    response = client.get(f"/api/runs/{uuid4()}")

    assert response.status_code == 404


def test_get_run_forbidden_returns_403(user_id: UUID, monkeypatch: MonkeyPatch) -> None:
    forbidden_id = str(uuid4())
    fake_db = FakeSupabaseClient(user_id, forbidden_ids={forbidden_id})
    app = create_app()

    def fake_current_user(request: Request) -> AuthenticatedUser:
        request.state.bearer_jwt = "test-jwt"
        return AuthenticatedUser(
            id=user_id,
            email="user@example.com",
            tier="free",
            monthly_runs_used=0,
            quota_remaining=50,
        )

    app.dependency_overrides[get_current_user] = fake_current_user
    monkeypatch.setattr(run_routes, "_client_for_request", lambda _request: fake_db)

    response = TestClient(app).get(f"/api/runs/{forbidden_id}")

    assert response.status_code == 403


def test_get_run_events_success(client: TestClient, fake_db: FakeSupabaseClient) -> None:
    created = client.post(
        "/api/runs",
        json={"input_source": "template", "template_name": "portfolio"},
    ).json()
    fake_db.insert(
        "run_events",
        {"run_id": created["run_id"], "event_type": "agent_started", "payload": {}},
    )

    response = client.get(f"/api/runs/{created['run_id']}/events")

    assert response.status_code == 200
    assert response.json()["items"][0]["event_type"] == "agent_started"


def test_get_run_events_validation_failure(client: TestClient) -> None:
    response = client.get(f"/api/runs/{uuid4()}/events?after_event_id=-1")

    assert response.status_code == 422


def test_delete_run_soft_deletes(client: TestClient) -> None:
    created = client.post(
        "/api/runs",
        json={"input_source": "template", "template_name": "portfolio"},
    ).json()

    response = client.delete(f"/api/runs/{created['run_id']}")

    assert response.status_code == 204
    assert client.get(f"/api/runs/{created['run_id']}").status_code == 404


def test_delete_run_validation_failure(client: TestClient) -> None:
    response = client.delete("/api/runs/not-a-uuid")

    assert response.status_code == 422


def test_export_endpoint_returns_501(client: TestClient) -> None:
    created = client.post(
        "/api/runs",
        json={"input_source": "template", "template_name": "portfolio"},
    ).json()

    response = client.post(f"/api/runs/{created['run_id']}/export", json={"format": "notebook"})

    assert response.status_code == 501
    assert response.json()["detail"] == "Export available in Day 4."


def test_export_validation_failure(client: TestClient) -> None:
    response = client.post(f"/api/runs/{uuid4()}/export", json={"format": "docx"})

    assert response.status_code == 422


def test_profile_success(client: TestClient) -> None:
    response = client.get("/api/profile")

    assert response.status_code == 200
    assert response.json()["quota_remaining"] == 47


def test_profile_without_auth_returns_401() -> None:
    response = TestClient(create_app()).get("/api/profile")

    assert response.status_code == 401


def test_templates_public_success() -> None:
    response = TestClient(create_app()).get("/api/templates")

    assert response.status_code == 200
    assert {item["name"] for item in response.json()["items"]} == {
        "portfolio",
        "max_cut",
        "knapsack",
    }
