from __future__ import annotations

from collections.abc import Iterator
from contextlib import suppress
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from infra.settings import Settings
from infra.supabase import get_anon_client, get_service_client, get_user_client

TestUser = dict[str, str]


@pytest.fixture()
def rls_users() -> Iterator[dict[str, TestUser]]:
    try:
        Settings()
    except ValidationError as exc:
        pytest.skip(f"Supabase credentials are not configured: {exc}")

    service = get_service_client()
    anon = get_anon_client()
    marker = uuid4().hex
    user_secret = f"QsimTest-{uuid4().hex}-42"
    emails = {
        "a": f"qsim-rls-a-{marker}@example.com",
        "b": f"qsim-rls-b-{marker}@example.com",
    }
    created_user_ids: list[str] = []
    try:
        users: dict[str, TestUser] = {}
        for label, email in emails.items():
            response = service.auth.admin.create_user(
                {
                    "email": email,
                    "password": user_secret,
                    "email_confirm": True,
                    "user_metadata": {"display_name": f"RLS User {label.upper()}"},
                }
            )
            user_id = str(response.user.id)
            created_user_ids.append(user_id)
            session_response = anon.auth.sign_in_with_password(
                {"email": email, "password": user_secret}
            )
            if session_response.session is None:
                raise RuntimeError("Supabase did not return a session for test user")
            users[label] = {
                "id": user_id,
                "email": email,
                "access_token": session_response.session.access_token,
            }
        yield users
    finally:
        for user_id in created_user_ids:
            service.auth.admin.delete_user(user_id)


def _insert_run(access_token: str, user_id: str) -> str:
    client = get_user_client(access_token)
    response = (
        client.table("runs")
        .insert(
            {
                "user_id": user_id,
                "template": "portfolio",
                "input_source": "template",
                "problem_ir": {"name": "portfolio", "variables": 6},
            }
        )
        .execute()
    )
    return str(response.data[0]["id"])


def test_user_b_cannot_select_user_a_run(rls_users: dict[str, TestUser]) -> None:
    user_a = rls_users["a"]
    user_b = rls_users["b"]
    run_id = _insert_run(str(user_a["access_token"]), str(user_a["id"]))

    user_b_client = get_user_client(str(user_b["access_token"]))
    response = user_b_client.table("runs").select("*").eq("id", run_id).execute()

    assert response.data == []


def test_user_b_cannot_select_user_a_events(rls_users: dict[str, TestUser]) -> None:
    user_a = rls_users["a"]
    user_b = rls_users["b"]
    run_id = _insert_run(str(user_a["access_token"]), str(user_a["id"]))
    service = get_service_client()
    service.table("run_events").insert(
        {"run_id": run_id, "event_type": "agent_started", "payload": {"agent": "penalty"}}
    ).execute()

    user_b_client = get_user_client(str(user_b["access_token"]))
    response = user_b_client.table("run_events").select("*").eq("run_id", run_id).execute()

    assert response.data == []


def test_user_b_cannot_insert_run_for_user_a(rls_users: dict[str, TestUser]) -> None:
    user_a = rls_users["a"]
    user_b = rls_users["b"]
    user_b_client = get_user_client(str(user_b["access_token"]))

    with pytest.raises(Exception, match="row-level security|violates"):
        user_b_client.table("runs").insert(
            {
                "user_id": str(user_a["id"]),
                "template": "portfolio",
                "input_source": "template",
                "problem_ir": {"name": "portfolio"},
            }
        ).execute()


def test_user_b_cannot_delete_user_a_run(rls_users: dict[str, TestUser]) -> None:
    user_a = rls_users["a"]
    user_b = rls_users["b"]
    run_id = _insert_run(str(user_a["access_token"]), str(user_a["id"]))
    user_b_client = get_user_client(str(user_b["access_token"]))

    with suppress(Exception):
        user_b_client.table("runs").delete().eq("id", run_id).execute()

    user_a_client = get_user_client(str(user_a["access_token"]))
    response = user_a_client.table("runs").select("id").eq("id", run_id).execute()
    assert response.data == [{"id": run_id}]


def test_user_a_can_soft_delete_own_run(rls_users: dict[str, TestUser]) -> None:
    user_a = rls_users["a"]
    run_id = _insert_run(str(user_a["access_token"]), str(user_a["id"]))
    user_a_client = get_user_client(str(user_a["access_token"]))
    deleted_at = datetime.now(tz=UTC).isoformat()

    user_a_client.table("runs").update({"deleted_at": deleted_at}).eq("id", run_id).execute()

    hidden_response = user_a_client.table("runs").select("id").eq("id", run_id).execute()
    service_response = (
        get_service_client().table("runs").select("deleted_at").eq("id", run_id).execute()
    )
    assert hidden_response.data == []
    assert service_response.data[0]["deleted_at"] is not None


def test_service_role_can_manage_rls_protected_rows(rls_users: dict[str, TestUser]) -> None:
    user_a = rls_users["a"]
    service = get_service_client()
    run_response = (
        service.table("runs")
        .insert(
            {
                "user_id": str(user_a["id"]),
                "template": "knapsack",
                "input_source": "template",
                "problem_ir": {"name": "knapsack"},
            }
        )
        .execute()
    )
    run_id = str(run_response.data[0]["id"])

    service.table("run_events").insert(
        {"run_id": run_id, "event_type": "pipeline_done", "payload": {}}
    ).execute()
    service.table("exports").insert({"run_id": run_id, "format": "notebook"}).execute()
    service.table("rate_limit_log").insert(
        {"user_id": str(user_a["id"]), "action": "create_run"}
    ).execute()
    update_response = service.table("runs").update({"status": "done"}).eq("id", run_id).execute()

    assert update_response.data[0]["status"] == "done"
